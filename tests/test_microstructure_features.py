"""Tests for microstructure feature generation and integration."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.features.microstructure_features import MicrostructureFeatures


def _base_df(rows: int = 120) -> pd.DataFrame:
    ts = pd.date_range("2026-02-23T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    base = 2050 + np.cumsum(np.random.default_rng(11).normal(0, 0.4, rows))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": base + np.random.default_rng(12).normal(0, 0.1, rows),
            "high": base + np.abs(np.random.default_rng(13).normal(0.25, 0.15, rows)),
            "low": base - np.abs(np.random.default_rng(14).normal(0.25, 0.15, rows)),
            "close": base,
            "volume": np.random.default_rng(15).integers(600, 2400, rows),
        },
        index=ts,
    )


def test_microstructure_features_from_l1_l2_columns() -> None:
    df = _base_df()
    rng = np.random.default_rng(21)
    df["l1_spread_pips"] = np.clip(rng.normal(3.0, 1.0, len(df)), 0.2, None)
    df["l2_order_imbalance"] = np.tanh(rng.normal(0.0, 1.1, len(df)))
    df["l2_depth_ratio"] = np.clip(rng.lognormal(0.0, 0.6, len(df)), 0.15, 8.0)

    micro = MicrostructureFeatures()
    out = micro.calculate(df)
    feature_cols = micro.get_feature_names()

    assert set(feature_cols).issubset(out.columns)
    assert out[feature_cols].isna().sum().sum() == 0
    assert float(out["micro_liquidity_stress"].std()) > 0.0
    assert float(out["micro_pressure"].abs().max()) > 0.0


def test_microstructure_features_safe_defaults_without_l1_l2_columns() -> None:
    df = _base_df()
    micro = MicrostructureFeatures()
    out = micro.calculate(df)
    feature_cols = micro.get_feature_names()

    assert set(feature_cols).issubset(out.columns)
    assert out[feature_cols].isna().sum().sum() == 0
    assert (out["l1_spread_pips"] > 0).all()


def test_feature_engineer_exposes_microstructure_group() -> None:
    engineer = FeatureEngineer()
    groups = engineer.get_feature_groups()

    assert "microstructure" in groups
    assert len(groups["microstructure"]) >= 3
    assert set(groups["microstructure"]).issubset(set(engineer.get_feature_names()))

