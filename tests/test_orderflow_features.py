"""Tests for OHLCV-derived order-flow features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.features.microstructure_features import MicrostructureFeatures
from ai_engine.features.orderflow_features import OrderFlowFeatures


def _base_df(rows: int = 260) -> pd.DataFrame:
    ts = pd.date_range("2026-02-23T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(1301)
    close = 2050.0 + np.cumsum(rng.normal(0.0, 0.35, rows))
    open_ = close + rng.normal(0.0, 0.12, rows)
    high = np.maximum(open_, close) + np.abs(rng.normal(0.25, 0.08, rows))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.25, 0.08, rows))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(700, 2600, rows),
        },
        index=ts,
    )


def test_feature_names_are_flow_prefixed_and_do_not_overlap_microstructure() -> None:
    names = OrderFlowFeatures().get_feature_names()
    micro_names = set(MicrostructureFeatures().get_feature_names())

    assert len(names) == len(set(names))
    assert all(name.startswith("flow_") for name in names)
    assert not set(names) & micro_names


def test_calculate_ohlcv_only_creates_all_flow_columns() -> None:
    df = _base_df()
    features = OrderFlowFeatures()
    out = features.calculate(df)

    assert set(features.get_feature_names()).issubset(out.columns)
    assert out[features.get_feature_names()].isna().sum().sum() == 0
    assert np.isfinite(out[features.get_feature_names()].to_numpy()).all()


def test_delta_direction_and_doji_safety() -> None:
    df = _base_df(80)
    df.loc[df.index[10], ["open", "high", "low", "close"]] = [2050.0, 2050.0, 2050.0, 2050.0]
    df.loc[df.index[20], ["open", "high", "low", "close", "volume"]] = [
        2050.0,
        2052.0,
        2049.5,
        2051.5,
        1000,
    ]
    df.loc[df.index[21], ["open", "high", "low", "close", "volume"]] = [
        2051.5,
        2052.0,
        2049.0,
        2049.5,
        1000,
    ]

    out = OrderFlowFeatures().calculate(df)

    assert np.isfinite(out.loc[df.index[10], "flow_delta"])
    assert out.loc[df.index[20], "flow_delta"] > 0.0
    assert out.loc[df.index[21], "flow_delta"] < 0.0
    assert out["flow_buy_pressure"].between(-1.0, 1.0).all()


def test_cumulative_delta_and_divergence_are_materialized() -> None:
    df = _base_df()
    out = OrderFlowFeatures().calculate(df)

    assert "flow_delta_cumulative_20" in out.columns
    assert "flow_delta_divergence" in out.columns
    assert out["flow_delta_cumulative_20"].abs().max() > 0.0
    assert out["flow_delta_divergence"].between(-2.0, 2.0).all()


def test_volume_profile_distances_exist_after_warmup() -> None:
    df = _base_df(260)
    out = OrderFlowFeatures(profile_window=80, profile_bins=24).calculate(df)
    tail = out.tail(60)

    assert tail["flow_poc_distance"].abs().max() > 0.0
    assert np.isfinite(tail[["flow_poc_distance", "flow_vah_distance", "flow_val_distance"]].to_numpy()).all()


def test_liquidity_zone_and_absorption_features() -> None:
    df = _base_df(160)
    df.loc[df.index[60:65], "high"] += 4.0
    df.loc[df.index[90:95], "low"] -= 4.0
    df.loc[df.index[120], "volume"] = df["volume"].max() * 8
    df.loc[df.index[120], "close"] = df.loc[df.index[120], "open"] + 0.01

    out = OrderFlowFeatures(liquidity_window=20, absorption_window=20).calculate(df)

    assert out["flow_liq_zone_above"].max() >= 0.0
    assert out["flow_liq_zone_below"].max() >= 0.0
    assert out["flow_absorption_score"].abs().max() > 0.0
    assert out["flow_absorption_score"].between(-5.0, 5.0).all()


def test_optional_l1_imbalance_columns_default_to_neutral() -> None:
    df = _base_df(80)
    out = OrderFlowFeatures().calculate(df)

    assert out["flow_l1_imbalance"].eq(0.0).all()
    assert out["flow_l1_imbalance_ema_10"].eq(0.0).all()


def test_optional_l1_imbalance_is_clipped_and_smoothed() -> None:
    df = _base_df(80)
    df["flow_l1_imbalance"] = np.linspace(-2.0, 2.0, len(df))

    out = OrderFlowFeatures().calculate(df)

    assert out["flow_l1_imbalance"].between(-1.0, 1.0).all()
    assert out["flow_l1_imbalance_ema_10"].between(-1.0, 1.0).all()


def test_future_row_mutation_does_not_change_closed_candle_outputs() -> None:
    df = _base_df(140)
    baseline = OrderFlowFeatures().calculate(df)
    mutated = df.copy()
    mutated.loc[mutated.index[-20:], ["high", "low", "close", "volume"]] = [
        3000.0,
        1000.0,
        2500.0,
        999999.0,
    ]

    changed = OrderFlowFeatures().calculate(mutated)
    checked_cols = ["flow_fvg_above", "flow_fvg_below", "flow_liq_zone_above", "flow_liq_zone_below"]

    pd.testing.assert_frame_equal(
        baseline.loc[baseline.index[:80], checked_cols],
        changed.loc[changed.index[:80], checked_cols],
    )
