"""Focused tests for regime-aware threshold artifacts."""

import numpy as np

from ai_engine.calibration.artifacts import load_threshold_artifact, write_threshold_artifact
from ai_engine.calibration.threshold_tuner import lookup_threshold, tune_thresholds


def _sample_probabilities() -> np.ndarray:
    return np.array(
        [
            [0.82, 0.10, 0.08],
            [0.72, 0.15, 0.13],
            [0.12, 0.74, 0.14],
            [0.10, 0.18, 0.72],
            [0.14, 0.20, 0.66],
            [0.64, 0.18, 0.18],
            [0.16, 0.18, 0.66],
            [0.18, 0.62, 0.20],
            [0.70, 0.18, 0.12],
            [0.12, 0.12, 0.76],
        ],
        dtype=np.float64,
    )


def _sample_labels() -> np.ndarray:
    return np.array([-1, -1, 0, 1, 1, -1, 1, 0, -1, 1], dtype=np.int64)


def test_tune_thresholds_returns_versioned_schema() -> None:
    artifact = tune_thresholds(
        y_true=_sample_labels(),
        y_probs=_sample_probabilities(),
        model_name="xgboost",
        min_support=2,
    )

    assert artifact["schema_version"] == 1
    assert artifact["class_labels"] == ["SELL", "HOLD", "BUY"]
    assert "global" in artifact["thresholds"]
    assert "BUY" in artifact["thresholds"]["global"]
    assert "SELL" in artifact["thresholds"]["global"]


def test_lookup_threshold_falls_back_to_global_then_ranging() -> None:
    artifact = tune_thresholds(
        y_true=_sample_labels(),
        y_probs=_sample_probabilities(),
        regimes=["trending", "trending", "ranging", "ranging", "volatile", "volatile", "ranging", "ranging", "trending", "volatile"],
        model_name="lightgbm",
        min_support=2,
    )

    global_buy = lookup_threshold(artifact, regime="unknown", action="BUY")
    assert global_buy["threshold_source"] == "global"

    artifact["thresholds"].pop("global")
    artifact["thresholds"].pop("volatile")
    fallback_buy = lookup_threshold(artifact, regime="volatile", action="BUY")
    assert fallback_buy["threshold_source"] == "ranging"


def test_threshold_artifact_round_trip_from_directory(tmp_path) -> None:
    artifact = tune_thresholds(
        y_true=_sample_labels(),
        y_probs=_sample_probabilities(),
        model_name="xgboost",
        min_support=2,
    )

    write_threshold_artifact(str(tmp_path), artifact)
    loaded = load_threshold_artifact(str(tmp_path))

    assert loaded["source"]["model_name"] == "xgboost"
    assert loaded["thresholds"]["global"]["BUY"]["min_confidence"] >= 0.34
