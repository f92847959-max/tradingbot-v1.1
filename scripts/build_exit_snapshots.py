r"""Generate Exit-AI training snapshots from a bulk OHLCV CSV.

Reads `data/gold_<tf>.csv` (raw OHLCV from Dukascopy bulk fetch), simulates
virtual ATR-based BUY+SELL trades along the bar history, and emits one
snapshot CSV with all columns required by `scripts/train_exit_ai.py`:

    timestamp, direction, entry_price, current_price,
    current_stop_loss, initial_stop_loss, take_profit,
    atr, regime, tp1, hours_open, volume_ratio, spread_pips,
    support_level, resistance_level, reversal_exit, already_closed,
    future_adverse_r, future_favorable_r, future_return_r

Causal/leak-safe: features at bar `t` use only bars <= t, future_*_r use
only bars > t. Indicators are computed once via market_data.indicators
when atr_14 is missing in the input CSV.

Examples:
    python scripts/build_exit_snapshots.py
    python scripts/build_exit_snapshots.py --csv data/gold_5m.csv --stride 4
    python scripts/build_exit_snapshots.py --csv data/gold_15m.csv \
        --tp-atr-mult 2.0 --sl-atr-mult 1.5 --max-holding 15
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from market_data.indicators import calculate_indicators  # noqa: E402

DEFAULT_CSV = ROOT / "data" / "gold_5m.csv"
DEFAULT_OUTPUT = ROOT / "data" / "exit_ai_snapshots.csv"
DEFAULT_STRIDE = 4
DEFAULT_TP_ATR = 2.0
DEFAULT_SL_ATR = 1.5
DEFAULT_MAX_HOLDING = 15
DEFAULT_SNAPSHOT_OFFSETS = (3, 7, 11)
DEFAULT_LOOKAHEAD = 20
TIMEFRAME_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440,
}


def _infer_timeframe_minutes(csv_path: Path) -> int:
    name = csv_path.stem.lower()
    for tf, minutes in TIMEFRAME_MINUTES.items():
        if name.endswith(f"_{tf}"):
            return minutes
    return 5


def _ensure_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if "atr_14" in df.columns and "rsi_14" in df.columns:
        return df
    print("INFO: atr_14 missing -> running calculate_indicators() on input frame")
    return calculate_indicators(df)


def _load_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Input OHLCV CSV not found: {csv_path}")
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        raise ValueError(f"{csv_path}: missing 'timestamp' column")
    for col in ("open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"{csv_path}: missing OHLC column '{col}'")
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)
    return df


def _regime_label(adx: float | None) -> str:
    if adx is None or not np.isfinite(adx):
        return "RANGING"
    return "TRENDING" if adx >= 20.0 else "RANGING"


def _support_resistance(prev: pd.DataFrame) -> tuple[float, float]:
    if prev.empty:
        return 0.0, 0.0
    window = prev.tail(20)
    return float(window["low"].min()), float(window["high"].max())


def _reversal_signal(prev: pd.DataFrame, direction: str) -> bool:
    if len(prev) < 4:
        return False
    last4 = prev.tail(4)
    diffs = last4["close"].diff().dropna()
    if len(diffs) < 3:
        return False
    if direction == "BUY":
        return bool((diffs.iloc[-3:] < 0).all())
    return bool((diffs.iloc[-3:] > 0).all())


def _hours_open(open_ts: pd.Timestamp, current_ts: pd.Timestamp) -> float:
    delta = current_ts - open_ts
    return float(delta.total_seconds() / 3600.0)


def _signed_profit_r(direction: str, entry: float, price: float, risk: float) -> float:
    move = (price - entry) if direction == "BUY" else (entry - price)
    if risk <= 0:
        return 0.0
    return float(move / risk)


def _trade_high_low(direction: str, future: pd.DataFrame) -> tuple[float, float]:
    if future.empty:
        return 0.0, 0.0
    if direction == "BUY":
        return float(future["high"].max()), float(future["low"].min())
    return float(future["low"].min()), float(future["high"].max())


def _build_one_snapshot(
    *,
    df: pd.DataFrame,
    open_idx: int,
    current_idx: int,
    direction: str,
    tp_atr: float,
    sl_atr: float,
    max_holding: int,
    lookahead: int,
) -> dict | None:
    open_row = df.iloc[open_idx]
    atr = float(open_row.get("atr_14", float("nan")))
    if not np.isfinite(atr) or atr <= 0:
        return None
    entry_price = float(open_row["close"])
    sl_dist = atr * sl_atr
    tp_dist = atr * tp_atr
    if direction == "BUY":
        initial_sl = entry_price - sl_dist
        take_profit = entry_price + tp_dist
    else:
        initial_sl = entry_price + sl_dist
        take_profit = entry_price - tp_dist
    tp1 = (entry_price + (sl_dist * 1.5)) if direction == "BUY" \
        else (entry_price - (sl_dist * 1.5))

    cur_row = df.iloc[current_idx]
    current_price = float(cur_row["close"])
    current_stop = initial_sl
    profit_r = _signed_profit_r(direction, entry_price, current_price, sl_dist)

    prev = df.iloc[max(0, current_idx - 30): current_idx + 1]
    support, resistance = _support_resistance(prev)
    reversal = _reversal_signal(prev, direction)
    regime = _regime_label(cur_row.get("adx"))
    volume_ratio = 1.0
    if "volume" in df.columns:
        recent_vol = prev["volume"].tail(20).mean() if not prev.empty else 0.0
        cur_vol = float(cur_row["volume"]) if pd.notna(cur_row["volume"]) else 0.0
        if recent_vol > 0:
            volume_ratio = float(cur_vol / recent_vol)
    spread_pips = max(2.0, abs(float(cur_row["high"]) - float(cur_row["low"])) * 10.0)

    last_idx = min(open_idx + max_holding, len(df) - 1)
    trade_window = df.iloc[current_idx + 1: last_idx + 1]
    future_window = df.iloc[current_idx + 1: current_idx + 1 + lookahead]
    if future_window.empty or trade_window.empty:
        return None

    if direction == "BUY":
        adverse_excursion = entry_price - float(trade_window["low"].min())
        favorable_excursion = float(trade_window["high"].max()) - entry_price
    else:
        adverse_excursion = float(trade_window["high"].max()) - entry_price
        favorable_excursion = entry_price - float(trade_window["low"].min())

    exit_price = float(trade_window.iloc[-1]["close"])
    return_r = _signed_profit_r(direction, entry_price, exit_price, sl_dist)
    future_adverse_r = float(max(adverse_excursion / sl_dist, 0.0))
    future_favorable_r = float(max(favorable_excursion / sl_dist, 0.0))

    return {
        "timestamp": cur_row["timestamp"].isoformat(),
        "direction": direction,
        "regime": regime,
        "entry_price": round(entry_price, 4),
        "current_price": round(current_price, 4),
        "current_stop_loss": round(current_stop, 4),
        "initial_stop_loss": round(initial_sl, 4),
        "take_profit": round(take_profit, 4),
        "tp1": round(tp1, 4),
        "atr": round(atr, 4),
        "hours_open": round(_hours_open(open_row["timestamp"], cur_row["timestamp"]), 4),
        "volume_ratio": round(volume_ratio, 4),
        "spread_pips": round(spread_pips, 4),
        "support_level": round(support, 4),
        "resistance_level": round(resistance, 4),
        "reversal_exit": bool(reversal and profit_r > 0),
        "already_closed": False,
        "future_adverse_r": round(future_adverse_r, 4),
        "future_favorable_r": round(future_favorable_r, 4),
        "future_return_r": round(return_r, 4),
    }


def build_snapshots(
    df: pd.DataFrame,
    *,
    stride: int,
    tp_atr: float,
    sl_atr: float,
    max_holding: int,
    snapshot_offsets: tuple[int, ...],
    lookahead: int,
) -> pd.DataFrame:
    n = len(df)
    if n < max_holding + lookahead + 50:
        raise ValueError(
            f"Not enough rows ({n}) for max_holding={max_holding} + "
            f"lookahead={lookahead}"
        )

    open_indices = range(50, n - max_holding - lookahead, max(stride, 1))
    total = len(open_indices)
    print(f"Building snapshots: {total} virtual open-points x 2 directions "
          f"x {len(snapshot_offsets)} offsets")

    records: list[dict] = []
    progress_step = max(total // 20, 1)
    for i, open_idx in enumerate(open_indices):
        if i % progress_step == 0 and i > 0:
            pct = (i / total) * 100.0
            print(f"  [snap] {i}/{total} ({pct:.0f}%) - {len(records)} snapshots so far")
        for direction in ("BUY", "SELL"):
            for offset in snapshot_offsets:
                cur_idx = open_idx + offset
                if cur_idx >= n - 1:
                    continue
                snapshot = _build_one_snapshot(
                    df=df,
                    open_idx=open_idx,
                    current_idx=cur_idx,
                    direction=direction,
                    tp_atr=tp_atr,
                    sl_atr=sl_atr,
                    max_holding=max_holding,
                    lookahead=lookahead,
                )
                if snapshot is not None:
                    records.append(snapshot)

    print(f"  [snap] done -> {len(records)} snapshots")
    if not records:
        raise RuntimeError("No snapshots produced (check ATR coverage / row count)")
    return pd.DataFrame.from_records(records)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate Exit-AI training snapshots from bulk OHLCV CSV.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE,
                        help="Open virtual trades every N bars")
    parser.add_argument("--tp-atr-mult", type=float, default=DEFAULT_TP_ATR)
    parser.add_argument("--sl-atr-mult", type=float, default=DEFAULT_SL_ATR)
    parser.add_argument("--max-holding", type=int, default=DEFAULT_MAX_HOLDING)
    parser.add_argument("--lookahead", type=int, default=DEFAULT_LOOKAHEAD,
                        help="Bars after snapshot used for future_*_r")
    parser.add_argument(
        "--snapshot-offsets",
        default=",".join(str(x) for x in DEFAULT_SNAPSHOT_OFFSETS),
        help="Comma-separated bar offsets into the trade where snapshots are taken",
    )
    parser.add_argument("--max-rows", type=int, default=0,
                        help="Cap on total snapshots (0 = no cap, takes head)")
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    out_path = Path(args.output).resolve()
    offsets = tuple(int(x) for x in args.snapshot_offsets.split(",") if x.strip())

    print(f"Input OHLCV: {csv_path}")
    df = _load_csv(csv_path)
    print(f"Loaded {len(df)} rows ({df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]})")

    df = _ensure_indicators(df)
    if "atr_14" not in df.columns:
        print("ERROR: atr_14 column not produced by calculate_indicators()")
        return 1

    snapshots = build_snapshots(
        df,
        stride=max(args.stride, 1),
        tp_atr=args.tp_atr_mult,
        sl_atr=args.sl_atr_mult,
        max_holding=args.max_holding,
        snapshot_offsets=offsets,
        lookahead=args.lookahead,
    )

    if args.max_rows > 0 and len(snapshots) > args.max_rows:
        print(f"Capping snapshots to {args.max_rows} (was {len(snapshots)})")
        snapshots = snapshots.head(args.max_rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_csv(out_path, index=False)
    print(f"Wrote {len(snapshots)} snapshots -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
