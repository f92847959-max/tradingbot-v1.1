r"""Bulk-download multi-year XAU/USD historical candles from Dukascopy.

Writes CSVs in the format scripts/train_models.py consumes via --csv,
matching the start_ai_training.py default save paths so a subsequent run of:

    python start_ai_training.py --use-csv-if-present

picks up the bulk dataset instead of calling the Capital.com broker.

Why Dukascopy:
    - free, no account required
    - XAU/USD (spot gold) history since 1999-06-03
    - tick / 1m / 5m / 1h aggregations available
    - returns pandas DataFrames directly

Examples:
    python scripts/fetch_bulk_history.py --years 2
    python scripts/fetch_bulk_history.py --start 2022-01-01 --end 2026-04-01
    python scripts/fetch_bulk_history.py --timeframes 1m,5m,15m,1h --output-dir data
    python scripts/fetch_bulk_history.py --years 5 --base-timeframe 1m --resample-from-base

Notes:
    - Downloads in monthly chunks with retries to avoid timeouts.
    - Already-fetched months are skipped if the output CSV already covers them.
    - When --resample-from-base is set, only the base timeframe is fetched and
      higher timeframes are derived locally (faster, fewer API calls).
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR_DEFAULT = ROOT / "data"
DEFAULT_TIMEFRAMES = ("1m", "5m", "15m", "1h")

INSTRUMENT = "XAU/USD"

PANDAS_RESAMPLE_RULE = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1d": "1D",
}

OHLCV_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


@dataclass(frozen=True)
class FetchPlan:
    timeframe: str
    start: datetime
    end: datetime
    output_csv: Path


def _import_dukascopy():
    try:
        import dukascopy_python  # type: ignore
    except ImportError as exc:
        print(
            "ERROR: dukascopy-python is not installed.\n"
            "Install it with:\n"
            "    pip install dukascopy-python>=4.0.1\n"
            f"(import error: {exc})"
        )
        sys.exit(1)
    return dukascopy_python


def _interval_constant(dukascopy_python, timeframe: str):
    mapping = {
        "1m": "INTERVAL_MIN_1",
        "5m": "INTERVAL_MIN_5",
        "15m": "INTERVAL_MIN_15",
        "30m": "INTERVAL_MIN_30",
        "1h": "INTERVAL_HOUR_1",
        "4h": "INTERVAL_HOUR_4",
        "1d": "INTERVAL_DAY_1",
    }
    name = mapping.get(timeframe)
    if name is None or not hasattr(dukascopy_python, name):
        raise ValueError(
            f"Unsupported / unknown Dukascopy interval for timeframe '{timeframe}'. "
            f"Update mapping in {Path(__file__).name}."
        )
    return getattr(dukascopy_python, name)


def _parse_timeframes(raw: str) -> list[str]:
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("At least one timeframe is required (--timeframes)")
    bad = [tf for tf in values if tf not in PANDAS_RESAMPLE_RULE]
    if bad:
        raise ValueError(
            f"Unknown timeframes: {bad}. "
            f"Supported: {', '.join(PANDAS_RESAMPLE_RULE)}"
        )
    seen: set[str] = set()
    unique: list[str] = []
    for tf in values:
        if tf in seen:
            continue
        seen.add(tf)
        unique.append(tf)
    return unique


def _safe_timeframe_name(timeframe: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in timeframe)


def _output_csv(output_dir: Path, timeframe: str) -> Path:
    return output_dir / f"gold_{_safe_timeframe_name(timeframe)}.csv"


def _resolve_date_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.start and args.end:
        start = pd.Timestamp(args.start, tz="UTC").to_pydatetime()
        end = pd.Timestamp(args.end, tz="UTC").to_pydatetime()
    elif args.years:
        end = datetime.now(tz=timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        start = end - pd.DateOffset(years=args.years)
        start = pd.Timestamp(start).to_pydatetime()
    else:
        raise ValueError("Provide either --years N or both --start and --end")

    if start >= end:
        raise ValueError(f"start ({start}) must be before end ({end})")
    return start, end


def _month_chunks(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Split [start, end) into monthly chunks (UTC, half-open)."""
    chunks: list[tuple[datetime, datetime]] = []
    cursor_ts = pd.Timestamp(start)
    if cursor_ts.tz is None:
        cursor_ts = cursor_ts.tz_localize("UTC")
    end_ts = pd.Timestamp(end)
    if end_ts.tz is None:
        end_ts = end_ts.tz_localize("UTC")

    while cursor_ts < end_ts:
        next_month_ts = (
            (cursor_ts + pd.DateOffset(months=1))
            .normalize()
            .replace(day=1)
        )
        chunk_end_ts = min(next_month_ts, end_ts)
        chunks.append((cursor_ts.to_pydatetime(), chunk_end_ts.to_pydatetime()))
        cursor_ts = next_month_ts
    return chunks


def _fetch_chunk(
    dukascopy_python,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    retries: int,
    sleep_seconds: float,
) -> pd.DataFrame:
    interval = _interval_constant(dukascopy_python, timeframe)
    offer_side = dukascopy_python.OFFER_SIDE_BID

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            df = dukascopy_python.fetch(INSTRUMENT, interval, offer_side, start, end)
            if df is None or df.empty:
                return pd.DataFrame()
            return _normalise_frame(df)
        except Exception as exc:
            last_exc = exc
            wait = sleep_seconds * attempt
            print(
                f"    attempt {attempt}/{retries} failed: {exc} "
                f"(retry in {wait:.1f}s)"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Dukascopy fetch failed for {timeframe} {start.date()}..{end.date()}: "
        f"{last_exc}"
    )


def _normalise_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if not isinstance(out.index, pd.DatetimeIndex):
        if "timestamp" in out.columns:
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
            out = out.set_index("timestamp")
        else:
            raise ValueError(
                "Dukascopy frame has no DatetimeIndex and no 'timestamp' column"
            )

    if out.index.tz is None:
        out.index = out.index.tz_localize("UTC")
    else:
        out.index = out.index.tz_convert("UTC")

    out.index.name = "timestamp"

    rename_map = {c: c.lower() for c in out.columns}
    out = out.rename(columns=rename_map)

    expected = {"open", "high", "low", "close"}
    missing = expected.difference(out.columns)
    if missing:
        raise ValueError(f"Dukascopy frame missing OHLC columns: {sorted(missing)}")

    if "volume" not in out.columns:
        out["volume"] = 0.0

    return out[["open", "high", "low", "close", "volume"]]


def _load_existing(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        return pd.DataFrame()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp").sort_index()
    return df


def _resample(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    rule = PANDAS_RESAMPLE_RULE[timeframe]
    resampled = df.resample(rule, label="left", closed="left").agg(OHLCV_AGG)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    return resampled


def _write_csv(df: pd.DataFrame, csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df.to_csv(csv_path)


def _fetch_timeframe_directly(
    dukascopy_python,
    timeframe: str,
    start: datetime,
    end: datetime,
    csv_path: Path,
    *,
    retries: int,
    sleep_seconds: float,
) -> pd.DataFrame:
    existing = _load_existing(csv_path)
    chunks = _month_chunks(start, end)
    pieces: list[pd.DataFrame] = [existing] if not existing.empty else []

    for idx, (chunk_start, chunk_end) in enumerate(chunks, start=1):
        if not existing.empty:
            existing_min = existing.index.min()
            existing_max = existing.index.max()
            chunk_start_ts = pd.Timestamp(chunk_start)
            chunk_end_ts = pd.Timestamp(chunk_end)
            fully_covered = (
                existing_min <= chunk_start_ts and chunk_end_ts <= existing_max
            )
            if fully_covered:
                print(
                    f"  [{timeframe}] {chunk_start.date()}..{chunk_end.date()} "
                    f"({idx}/{len(chunks)}) already covered, skipping"
                )
                continue
        print(
            f"  [{timeframe}] {chunk_start.date()}..{chunk_end.date()} "
            f"({idx}/{len(chunks)}) fetching..."
        )
        chunk_df = _fetch_chunk(
            dukascopy_python, timeframe, chunk_start, chunk_end,
            retries=retries, sleep_seconds=sleep_seconds,
        )
        if chunk_df.empty:
            print(f"    no candles returned for {timeframe} chunk")
            continue
        pieces.append(chunk_df)

    if not pieces:
        print(f"  [{timeframe}] no data to write")
        return pd.DataFrame()

    combined = pd.concat(pieces).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    _write_csv(combined, csv_path)
    print(f"  [{timeframe}] wrote {len(combined)} rows -> {csv_path}")
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk-download XAU/USD candles from Dukascopy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--years", type=int, default=None)
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD UTC")
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD UTC")
    parser.add_argument(
        "--timeframes",
        type=str,
        default=",".join(DEFAULT_TIMEFRAMES),
        help="Comma-separated output timeframes",
    )
    parser.add_argument(
        "--base-timeframe", type=str, default="1m",
        help="Base timeframe to fetch when resampling locally",
    )
    parser.add_argument(
        "--resample-from-base", action="store_true",
        help=(
            "Fetch only --base-timeframe from Dukascopy and resample higher "
            "timeframes locally (faster, fewer API calls)."
        ),
    )
    parser.add_argument("--output-dir", type=str, default=str(DATA_DIR_DEFAULT))
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument(
        "--sleep-seconds", type=float, default=2.0,
        help="Backoff base between retries (multiplied by attempt number).",
    )
    args = parser.parse_args()

    try:
        timeframes = _parse_timeframes(args.timeframes)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    try:
        start, end = _resolve_date_range(args)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.resample_from_base and args.base_timeframe not in PANDAS_RESAMPLE_RULE:
        print(f"ERROR: --base-timeframe '{args.base_timeframe}' is not supported")
        return 2

    output_dir = Path(args.output_dir)
    print("Bulk Dukascopy XAU/USD download")
    print(f"  range:        {start.isoformat()}  ->  {end.isoformat()}")
    print(f"  timeframes:   {', '.join(timeframes)}")
    print(f"  output:       {output_dir}")
    print(f"  resample:     {'yes (from ' + args.base_timeframe + ')' if args.resample_from_base else 'no'}")

    dukascopy_python = _import_dukascopy()

    if args.resample_from_base:
        base_tf = args.base_timeframe
        base_csv = _output_csv(output_dir, base_tf)
        print(f"\nFetching base timeframe {base_tf} -> {base_csv}")
        base_df = _fetch_timeframe_directly(
            dukascopy_python, base_tf, start, end, base_csv,
            retries=args.retries, sleep_seconds=args.sleep_seconds,
        )
        if base_df.empty:
            print("ERROR: base timeframe fetch returned no data; aborting")
            return 1

        for tf in timeframes:
            if tf == base_tf:
                continue
            target_csv = _output_csv(output_dir, tf)
            print(f"\nResampling {base_tf} -> {tf} -> {target_csv}")
            resampled = _resample(base_df, tf)
            if resampled.empty:
                print(f"  [{tf}] resample produced no rows")
                continue
            _write_csv(resampled, target_csv)
            print(f"  [{tf}] wrote {len(resampled)} rows -> {target_csv}")
    else:
        for tf in timeframes:
            csv_path = _output_csv(output_dir, tf)
            print(f"\nFetching timeframe {tf} -> {csv_path}")
            _fetch_timeframe_directly(
                dukascopy_python, tf, start, end, csv_path,
                retries=args.retries, sleep_seconds=args.sleep_seconds,
            )

    print("\nDone. Run training with the cached data via:")
    print("  python start_ai_training.py --use-csv-if-present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
