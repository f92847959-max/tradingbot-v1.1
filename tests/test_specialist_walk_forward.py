"""Tests for leak-free specialist walk-forward comparison."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.training.specialist_pipeline import (
    compare_core_vs_specialist,
    compare_feature_sets,
)


def _comparison_df(rows: int = 480) -> pd.DataFrame:
    ts = pd.date_range("2026-04-05T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(909)
    slope = np.linspace(-1.8, 2.1, rows)
    seasonal = np.sin(np.linspace(0.0, 18.0 * np.pi, rows)) * 1.1
    close = 2052.0 + slope + seasonal + rng.normal(0.0, 0.10, rows)

    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": close + rng.normal(0.0, 0.04, rows),
            "high": close + np.abs(rng.normal(0.20, 0.07, rows)),
            "low": close - np.abs(rng.normal(0.20, 0.07, rows)),
            "close": close,
            "volume": rng.integers(650, 2600, rows),
            "atr_14": np.clip(rng.normal(1.10, 0.12, rows), 0.35, None),
            "rsi_14": rng.uniform(18.0, 82.0, rows),
            "macd_line": rng.normal(0.0, 0.22, rows),
            "macd_signal": rng.normal(0.0, 0.18, rows),
            "macd_hist": rng.normal(0.0, 0.08, rows),
            "ema_9": close + rng.normal(0.0, 0.04, rows),
            "ema_21": close + rng.normal(0.0, 0.04, rows),
            "ema_50": close + rng.normal(0.0, 0.04, rows),
            "ema_200": np.full(rows, 2049.0),
            "bb_width": rng.uniform(0.006, 0.017, rows),
            "bb_position": rng.uniform(0.0, 1.0, rows),
            "adx_14": rng.uniform(12.0, 42.0, rows),
            "stoch_k": rng.uniform(10.0, 90.0, rows),
            "stoch_d": rng.uniform(10.0, 90.0, rows),
            "pivot": np.full(rows, 2052.0),
            "pivot_s1": np.full(rows, 2047.0),
            "pivot_r1": np.full(rows, 2057.0),
            "vwap": np.full(rows, 2052.2),
        },
        index=ts,
    )

    forward = pd.Series(close, index=ts).shift(-6).ffill()
    delta = forward - close
    df["label"] = np.where(delta > 0.18, 1, np.where(delta < -0.18, -1, 0))
    return df


def test_compare_core_vs_specialist_reports_stable_schema() -> None:
    report = compare_core_vs_specialist(
        _comparison_df(),
        min_train_samples=120,
        min_test_samples=40,
    )

    assert report["schema_version"] == 1
    assert report["window_count"] >= 1
    assert "core" in report["comparison"]
    assert "core_plus_specialist" in report["comparison"]
    assert set(report["deltas"]) == {
        "profit_factor_delta",
        "drawdown_delta",
        "calibration_delta",
        "trade_count_retention",
    }


def test_compare_core_vs_specialist_preserves_purge_gap_and_train_only_scaling() -> None:
    report = compare_core_vs_specialist(
        _comparison_df(),
        purge_gap=14,
        min_train_samples=120,
        min_test_samples=40,
    )

    assert report["purge_gap"] == 14
    assert all(window["purge_gap"] == 14 for window in report["windows"])
    assert all(window["scaler_scope"] == "train_only" for window in report["windows"])


def test_compare_feature_sets_rejects_misaligned_frames() -> None:
    df = _comparison_df(rows=260)
    engineer = FeatureEngineer()
    featured = engineer.create_features(
        df.copy(),
        timeframe="5m",
        include_specialist=True,
    )
    core_names = engineer.get_feature_names()
    candidate_names = core_names + engineer.get_specialist_feature_names()

    core_frame = featured[core_names + ["label"]].iloc[20:].copy()
    candidate_frame = featured[candidate_names + ["label"]].iloc[21:].copy()

    with pytest.raises(ValueError, match="identical length"):
        compare_feature_sets(
            core_frame=core_frame,
            core_feature_names=core_names,
            candidate_frame=candidate_frame,
            candidate_feature_names=candidate_names,
            min_train_samples=80,
            min_test_samples=20,
        )
