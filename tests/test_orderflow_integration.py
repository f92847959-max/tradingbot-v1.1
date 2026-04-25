"""Integration tests for order-flow features in FeatureEngineer."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.features.microstructure_features import MicrostructureFeatures
from ai_engine.features.orderflow_features import OrderFlowFeatures


def _feature_df(rows: int = 260) -> pd.DataFrame:
    ts = pd.date_range("2026-02-23T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(1303)
    close = 2050.0 + np.cumsum(rng.normal(0.0, 0.3, rows))
    open_ = close + rng.normal(0.0, 0.1, rows)
    high = np.maximum(open_, close) + np.abs(rng.normal(0.22, 0.06, rows))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.22, 0.06, rows))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(700, 2600, rows),
            "rsi_14": rng.uniform(20, 80, rows),
            "macd_line": rng.normal(0.0, 0.5, rows),
            "macd_signal": rng.normal(0.0, 0.3, rows),
            "macd_hist": rng.normal(0.0, 0.2, rows),
            "ema_9": close + rng.normal(0.0, 0.08, rows),
            "ema_21": close + rng.normal(0.0, 0.10, rows),
            "ema_50": close + rng.normal(0.0, 0.14, rows),
            "ema_200": np.full(rows, 2045.0),
            "bb_width": rng.uniform(0.005, 0.02, rows),
            "bb_position": rng.uniform(0.0, 1.0, rows),
            "adx_14": rng.uniform(10, 50, rows),
            "atr_14": rng.uniform(0.5, 2.0, rows),
            "stoch_k": rng.uniform(10, 90, rows),
            "stoch_d": rng.uniform(10, 90, rows),
            "pivot": np.full(rows, 2050.0),
            "pivot_s1": np.full(rows, 2045.0),
            "pivot_r1": np.full(rows, 2055.0),
            "vwap": np.full(rows, 2050.5),
        },
        index=ts,
    )


def test_feature_engineer_exposes_orderflow_group() -> None:
    engineer = FeatureEngineer()
    groups = engineer.get_feature_groups()

    assert "orderflow" in groups
    assert set(groups["orderflow"]) == set(OrderFlowFeatures().get_feature_names())


def test_feature_engineer_feature_names_include_orderflow() -> None:
    engineer = FeatureEngineer()
    names = set(engineer.get_feature_names())

    assert set(OrderFlowFeatures().get_feature_names()).issubset(names)


def test_orderflow_features_do_not_overlap_microstructure_names() -> None:
    flow_names = set(OrderFlowFeatures().get_feature_names())
    micro_names = set(MicrostructureFeatures().get_feature_names())

    assert not flow_names & micro_names


def test_create_features_adds_flow_columns_on_ohlcv_data() -> None:
    engineer = FeatureEngineer()
    result = engineer.create_features(_feature_df(), timeframe="5m")
    flow_names = OrderFlowFeatures().get_feature_names()

    assert set(flow_names).issubset(result.columns)
    assert result[flow_names].isna().sum().sum() == 0
    assert np.isfinite(result[flow_names].to_numpy()).all()


def test_orderflow_features_are_part_of_default_ml_feature_list() -> None:
    engineer = FeatureEngineer()
    result = engineer.create_features(_feature_df(), timeframe="5m")
    feature_names = engineer.get_feature_names()
    flow_names = OrderFlowFeatures().get_feature_names()

    assert all(name in feature_names for name in flow_names)
    assert set(flow_names).issubset(result[feature_names].columns)
    assert len(feature_names) == len(set(feature_names))


def test_optional_quote_enrichment_flows_through_feature_engineer() -> None:
    df = _feature_df()
    df["flow_l1_imbalance"] = np.linspace(-0.8, 0.8, len(df))

    result = FeatureEngineer().create_features(df, timeframe="5m")

    assert result["flow_l1_imbalance"].between(-1.0, 1.0).all()
    assert result["flow_l1_imbalance_ema_10"].abs().max() > 0.0
