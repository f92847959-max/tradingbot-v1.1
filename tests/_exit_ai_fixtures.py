"""Shared fixtures for Exit-AI tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_exit_ai_frame(rows: int = 360) -> pd.DataFrame:
    """Create a deterministic snapshot dataset with all four action classes."""
    timestamps = pd.date_range(
        "2026-04-02T00:00:00Z",
        periods=rows,
        freq="5min",
        tz="UTC",
    )
    rng = np.random.default_rng(4242)
    records: list[dict[str, float | str | bool]] = []

    for idx, ts in enumerate(timestamps):
        direction = "BUY" if idx % 2 == 0 else "SELL"
        regime = "TRENDING" if idx % 3 else "RANGING"
        entry = 2051.0 + np.sin(idx / 16.0) * 2.0 + (idx * 0.008)
        base_risk = 0.95 + ((idx % 6) * 0.08)
        initial_stop = entry - base_risk if direction == "BUY" else entry + base_risk
        take_profit = entry + (base_risk * 3.0) if direction == "BUY" else entry - (base_risk * 3.0)
        tp1 = entry + (base_risk * 1.5) if direction == "BUY" else entry - (base_risk * 1.5)

        pattern = idx % 4
        if pattern == 0:
            profit_r = 0.20
            reversal_exit = False
            future_adverse_r = 0.40
            future_favorable_r = 0.55
        elif pattern == 1:
            profit_r = 1.25
            reversal_exit = False
            tp1 = entry + (base_risk * 1.9) if direction == "BUY" else entry - (base_risk * 1.9)
            future_adverse_r = 0.90
            future_favorable_r = 1.10
        elif pattern == 2:
            profit_r = 1.75
            reversal_exit = False
            future_adverse_r = 0.70
            future_favorable_r = 1.30
        else:
            profit_r = 0.55
            reversal_exit = True
            future_adverse_r = 1.00
            future_favorable_r = 0.35

        current_price = entry + (base_risk * profit_r) if direction == "BUY" else entry - (base_risk * profit_r)
        records.append(
            {
                "timestamp": ts.isoformat(),
                "direction": direction,
                "regime": regime,
                "entry_price": round(entry, 4),
                "current_price": round(current_price, 4),
                "current_stop_loss": round(initial_stop, 4),
                "initial_stop_loss": round(initial_stop, 4),
                "take_profit": round(take_profit, 4),
                "tp1": round(tp1, 4),
                "atr": round(0.95 + ((idx % 5) * 0.10), 4),
                "hours_open": round((idx % 24) * 0.25, 4),
                "volume_ratio": round(0.9 + ((idx % 5) * 0.15), 4),
                "spread_pips": round(2.0 + ((idx % 3) * 0.25), 4),
                "support_level": round(entry - (base_risk * 1.4), 4),
                "resistance_level": round(entry + (base_risk * 1.4), 4),
                "reversal_exit": reversal_exit,
                "already_closed": False,
                "future_adverse_r": round(future_adverse_r + rng.normal(0.0, 0.025), 4),
                "future_favorable_r": round(future_favorable_r + rng.normal(0.0, 0.025), 4),
                "future_return_r": round(
                    future_favorable_r - (future_adverse_r * 0.45),
                    4,
                ),
            }
        )
    return pd.DataFrame.from_records(records)
