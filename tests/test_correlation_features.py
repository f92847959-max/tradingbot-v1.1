"""Tests for correlation feature materialization and FeatureEngineer registration."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.features.correlation_features import CorrelationFeatures
from ai_engine.features.feature_engineer import FeatureEngineer
from correlation import compute_snapshot


EXPECTED_FEATURES = {
    "corr_dxy_20",
    "corr_dxy_60",
    "corr_dxy_120",
    "corr_us10y_20",
    "corr_us10y_60",
    "corr_us10y_120",
    "corr_silver_20",
    "corr_silver_60",
    "corr_silver_120",
    "corr_vix_20",
    "corr_vix_60",
    "corr_vix_120",
    "corr_sp500_20",
    "corr_sp500_60",
    "corr_sp500_120",
    "divergence_dxy",
    "divergence_us10y",
    "corr_regime",
    "lead_lag_silver",
    "lead_lag_dxy",
}


def _ohlcv_df(rows: int = 100) -> pd.DataFrame:
    ts = pd.date_range("2026-02-23T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(23)
    close = 2050.0 + np.cumsum(rng.normal(0.0, 0.25, rows))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": close + rng.normal(0.0, 0.08, rows),
            "high": close + np.abs(rng.normal(0.18, 0.05, rows)),
            "low": close - np.abs(rng.normal(0.18, 0.05, rows)),
            "close": close,
            "volume": rng.integers(600, 2400, rows),
        },
        index=ts,
    )


def _closes_df(rows: int = 200) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="D")
    base = np.linspace(0.0, 4.0 * np.pi, rows)
    rng = np.random.default_rng(41)
    gold = 2000.0 + np.sin(base) * 15.0 + rng.normal(0.0, 0.4, rows)
    return pd.DataFrame(
        {
            "dxy": 105.0 - np.sin(base) * 0.8 + rng.normal(0.0, 0.03, rows),
            "us10y": 4.2 - np.sin(base) * 0.05 + rng.normal(0.0, 0.01, rows),
            "silver": 30.0 + np.sin(base) * 1.6 + rng.normal(0.0, 0.08, rows),
            "vix": 18.0 - np.sin(base) * 0.5 + rng.normal(0.0, 0.05, rows),
            "sp500": 5800.0 + np.sin(base) * 25.0 + rng.normal(0.0, 1.5, rows),
            "gold": gold,
        },
        index=index,
    )


def test_feature_names() -> None:
    names = CorrelationFeatures().get_feature_names()

    assert len(names) == 20
    assert set(names) == EXPECTED_FEATURES


def test_none_snapshot() -> None:
    result = CorrelationFeatures().calculate(_ohlcv_df(), snapshot=None)

    for name in EXPECTED_FEATURES:
        assert name in result.columns
        assert result[name].eq(0.0).all()


def test_feature_engineer_group() -> None:
    engineer = FeatureEngineer()
    groups = engineer.get_feature_groups()

    assert "correlation" in groups
    assert len(groups["correlation"]) == 20
    assert set(groups["correlation"]) == EXPECTED_FEATURES


def test_no_nan() -> None:
    snapshot = compute_snapshot(_closes_df())
    result = CorrelationFeatures().calculate(_ohlcv_df(), snapshot=snapshot)

    corr_frame = result[list(EXPECTED_FEATURES)]
    assert corr_frame.isna().sum().sum() == 0
    assert (corr_frame.max() <= 1.0).all()
    assert (corr_frame.min() >= -1.0).all()
