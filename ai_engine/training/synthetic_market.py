"""
Synthetic market generator for stress training.

Creates regime-switching OHLCV data with:
- trend regimes (up/down)
- mean reversion regime
- high-volatility shock regimes
- random price gaps and heavy-tailed noise

This module is intentionally deterministic when `seed` is set.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class SyntheticMarketConfig:
    rows: int
    timeframe: str = "5m"
    seed: Optional[int] = None
    start_price: float = 2050.0
    switch_probability: float = 0.035
    shock_probability: float = 0.018
    gap_probability: float = 0.006
    volatility_scale: float = 1.0
    start_timestamp: Optional[datetime] = None


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    tf = str(timeframe).strip().lower()
    if tf.endswith("m"):
        return timedelta(minutes=int(tf[:-1]))
    if tf.endswith("h"):
        return timedelta(hours=int(tf[:-1]))
    if tf.endswith("d"):
        return timedelta(days=int(tf[:-1]))
    raise ValueError(f"Unsupported timeframe format: {timeframe}")


def generate_synthetic_market(config: SyntheticMarketConfig) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Generates a synthetic OHLCV market stream and metadata.
    """
    rows = int(config.rows)
    if rows <= 0:
        raise ValueError("rows must be > 0")

    vol_scale = float(config.volatility_scale)
    if vol_scale <= 0:
        raise ValueError("volatility_scale must be > 0")

    rng = np.random.default_rng(config.seed)
    step = timeframe_to_timedelta(config.timeframe)

    if config.start_timestamp is None:
        end = datetime.now(timezone.utc)
        start = end - (rows - 1) * step
    else:
        start = config.start_timestamp

    # Regimes are configured for percentage returns per candle.
    regimes = [
        {"name": "trend_up", "drift": 0.00035, "vol": 0.0017, "revert": 0.00, "shock_mult": 1.0},
        {"name": "trend_down", "drift": -0.00040, "vol": 0.0020, "revert": 0.00, "shock_mult": 1.1},
        {"name": "mean_revert", "drift": 0.00005, "vol": 0.0015, "revert": 0.35, "shock_mult": 0.8},
        {"name": "high_vol", "drift": 0.0, "vol": 0.0042, "revert": 0.10, "shock_mult": 1.8},
        {"name": "panic", "drift": -0.0012, "vol": 0.0065, "revert": 0.00, "shock_mult": 2.7},
        {"name": "meltup", "drift": 0.0010, "vol": 0.0058, "revert": 0.00, "shock_mult": 2.4},
    ]

    regime_idx = int(rng.integers(0, len(regimes)))
    price = float(max(1.0, config.start_price))
    anchor_price = price

    rows_out = []
    regime_counts = {regime["name"]: 0 for regime in regimes}

    for i in range(rows):
        if rng.random() < float(config.switch_probability):
            regime_idx = int(rng.integers(0, len(regimes)))
        regime = regimes[regime_idx]
        regime_name = str(regime["name"])
        regime_counts[regime_name] += 1

        if i > 0 and i % 720 == 0:
            anchor_price = price

        base_vol = float(regime["vol"]) * vol_scale
        mean_revert_component = float(regime["revert"]) * ((anchor_price / max(price, 1e-6)) - 1.0) * 0.02

        # Gap at open (overnight-like discontinuity).
        open_gap = 0.0
        if rng.random() < float(config.gap_probability):
            open_gap = float(rng.normal(0.0, base_vol * 3.0))

        open_price = max(0.1, price * (1.0 + open_gap))

        heavy_noise = float(rng.standard_t(df=3.0) * base_vol)
        shock = 0.0
        if rng.random() < float(config.shock_probability) * float(regime["shock_mult"]):
            shock = float(rng.normal(0.0, base_vol * 7.0))

        ret = float(regime["drift"]) + mean_revert_component + heavy_noise + shock
        ret = float(np.clip(ret, -0.12, 0.12))

        close_price = max(0.1, open_price * (1.0 + ret))

        intrabar = abs(ret) + abs(heavy_noise) * 1.2 + base_vol * 3.0
        upper_wick = abs(float(rng.normal(intrabar * 0.35, intrabar * 0.25)))
        lower_wick = abs(float(rng.normal(intrabar * 0.35, intrabar * 0.25)))

        high = max(open_price, close_price) * (1.0 + upper_wick)
        low = min(open_price, close_price) * (1.0 - lower_wick)
        low = max(0.05, low)
        high = max(high, low * 1.0001)

        # Stress-aware volume and pseudo micro-structure context.
        volume_base = 1200.0 * (1.0 + intrabar * 90.0 + abs(shock) * 120.0)
        volume = max(1.0, volume_base * float(rng.lognormal(mean=0.0, sigma=0.45)))

        spread_pips = max(0.2, (0.8 + intrabar * 120.0 + abs(shock) * 200.0))
        l2_order_imbalance = float(
            np.tanh(rng.normal(loc=np.sign(ret) * 0.7, scale=1.0))
        )
        l2_depth_ratio = float(np.clip(rng.lognormal(mean=0.0, sigma=0.55), 0.15, 8.0))

        timestamp = start + i * step
        rows_out.append(
            {
                "timestamp": timestamp,
                "open": float(open_price),
                "high": float(high),
                "low": float(low),
                "close": float(close_price),
                "volume": float(volume),
                "market_regime": regime_name,
                "l1_spread_pips": float(spread_pips),
                "l2_order_imbalance": l2_order_imbalance,
                "l2_depth_ratio": l2_depth_ratio,
            }
        )

        price = close_price

    out = pd.DataFrame(rows_out)
    meta: Dict[str, Any] = {
        "rows": int(rows),
        "timeframe": config.timeframe,
        "seed": config.seed,
        "start_price": config.start_price,
        "switch_probability": config.switch_probability,
        "shock_probability": config.shock_probability,
        "gap_probability": config.gap_probability,
        "volatility_scale": config.volatility_scale,
        "regime_counts": regime_counts,
        "start_timestamp": out["timestamp"].iloc[0].isoformat(),
        "end_timestamp": out["timestamp"].iloc[-1].isoformat(),
    }
    return out, meta
