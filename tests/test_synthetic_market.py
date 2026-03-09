"""Tests for synthetic stress market generation."""

from __future__ import annotations

import pandas as pd

from ai_engine.training.synthetic_market import (
    SyntheticMarketConfig,
    generate_synthetic_market,
    timeframe_to_timedelta,
)


def test_timeframe_to_timedelta() -> None:
    assert timeframe_to_timedelta("1m").total_seconds() == 60
    assert timeframe_to_timedelta("5m").total_seconds() == 300
    assert timeframe_to_timedelta("1h").total_seconds() == 3600
    assert timeframe_to_timedelta("1d").total_seconds() == 86400


def test_generate_synthetic_market_basic_shape_and_consistency() -> None:
    df, meta = generate_synthetic_market(
        SyntheticMarketConfig(
            rows=600,
            timeframe="5m",
            seed=7,
            volatility_scale=1.4,
        )
    )

    assert len(df) == 600
    assert set(["timestamp", "open", "high", "low", "close", "volume"]).issubset(df.columns)
    assert (df["high"] >= df["low"]).all()
    assert (df["volume"] > 0).all()
    assert pd.to_datetime(df["timestamp"], utc=True).is_monotonic_increasing
    assert len(meta["regime_counts"]) >= 5
    assert sum(meta["regime_counts"].values()) == 600
