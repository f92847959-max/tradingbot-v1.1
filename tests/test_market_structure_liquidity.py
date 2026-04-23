"""Tests for specialist market-structure/liquidity features."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.features.market_structure_liquidity import (
    MarketStructureLiquidityFeatures,
)


def _base_df(rows: int = 160) -> pd.DataFrame:
    ts = pd.date_range("2026-04-01T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(121)
    close = 2050.0 + np.cumsum(rng.normal(0.0, 0.35, rows))
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": close + rng.normal(0.0, 0.08, rows),
            "high": close + np.abs(rng.normal(0.22, 0.09, rows)),
            "low": close - np.abs(rng.normal(0.22, 0.09, rows)),
            "close": close,
            "volume": rng.integers(600, 2400, rows),
            "atr_14": np.clip(rng.normal(1.3, 0.2, rows), 0.4, None),
            "rsi_14": rng.uniform(20.0, 80.0, rows),
            "macd_line": rng.normal(0.0, 0.3, rows),
            "macd_signal": rng.normal(0.0, 0.2, rows),
            "macd_hist": rng.normal(0.0, 0.1, rows),
            "ema_9": close + rng.normal(0.0, 0.12, rows),
            "ema_21": close + rng.normal(0.0, 0.10, rows),
            "ema_50": close + rng.normal(0.0, 0.08, rows),
            "ema_200": np.full(rows, 2048.0),
            "bb_width": rng.uniform(0.005, 0.02, rows),
            "bb_position": rng.uniform(0.0, 1.0, rows),
            "adx_14": rng.uniform(10.0, 40.0, rows),
            "stoch_k": rng.uniform(10.0, 90.0, rows),
            "stoch_d": rng.uniform(10.0, 90.0, rows),
            "pivot": np.full(rows, 2050.0),
            "pivot_s1": np.full(rows, 2046.0),
            "pivot_r1": np.full(rows, 2054.0),
            "vwap": np.full(rows, 2050.5),
        },
        index=ts,
    )


def test_feature_names_and_deterministic_output() -> None:
    df = _base_df()
    features = MarketStructureLiquidityFeatures()

    out_a = features.calculate(df)
    out_b = features.calculate(df.copy())

    assert features.FEATURE_NAMES == features.get_feature_names()
    assert set(features.FEATURE_NAMES).issubset(out_a.columns)
    pdt.assert_frame_equal(out_a[features.FEATURE_NAMES], out_b[features.FEATURE_NAMES])


def test_future_row_mutation_does_not_change_historical_specialist_features() -> None:
    df = _base_df()
    features = MarketStructureLiquidityFeatures()

    baseline = features.calculate(df.copy()).iloc[:100][features.FEATURE_NAMES]
    mutated = df.copy()
    mutated.iloc[120:, mutated.columns.get_loc("high")] *= 4.0
    mutated.iloc[120:, mutated.columns.get_loc("low")] *= 0.75
    mutated.iloc[120:, mutated.columns.get_loc("close")] *= 1.05
    changed = features.calculate(mutated).iloc[:100][features.FEATURE_NAMES]

    pdt.assert_frame_equal(baseline, changed)


def test_detects_sweeps_and_fvg_edges() -> None:
    df = _base_df(rows=60)
    idx = df.index

    df.loc[idx[20], ["high", "close"]] = [2055.0, 2054.8]
    df.loc[idx[21], ["high", "close"]] = [2054.6, 2054.2]
    df.loc[idx[22], ["high", "close"]] = [2056.0, 2053.6]

    df.loc[idx[28], "high"] = 2050.0
    df.loc[idx[30], "low"] = 2052.8

    features = MarketStructureLiquidityFeatures(swing_window=2)
    out = features.calculate(df)

    assert int(out["ms_buy_side_sweep"].sum()) >= 1
    assert float(out["ms_bull_fvg_size_atr"].max()) > 0.0
    assert float(out["ms_upper_wick_atr"].max()) > 0.0


def test_feature_engineer_baseline_unchanged_when_specialist_disabled() -> None:
    df = _base_df()
    engineer = FeatureEngineer()

    baseline = engineer.create_features(df.copy(), timeframe="5m")
    with_specialist = engineer.create_features(
        df.copy(),
        timeframe="5m",
        include_specialist=True,
    )

    base_feature_names = engineer.get_feature_names()
    specialist_names = engineer.get_specialist_feature_names()

    assert "market_structure_liquidity" in engineer.get_feature_groups()
    assert set(specialist_names).issubset(with_specialist.columns)
    assert not any(name in baseline.columns for name in specialist_names)
    pdt.assert_frame_equal(
        baseline[base_feature_names],
        with_specialist[base_feature_names],
    )
