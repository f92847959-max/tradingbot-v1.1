"""Focused tests for probability calibration helpers."""

import joblib
import numpy as np

from ai_engine.calibration.artifacts import CLASS_LABELS
from ai_engine.calibration.calibrator import (
    apply_calibrator,
    fit_calibrator,
    load_calibrator,
)
from ai_engine.calibration.metrics import compute_calibration_metrics


def _sample_probabilities() -> np.ndarray:
    return np.array(
        [
            [0.82, 0.10, 0.08],
            [0.75, 0.18, 0.07],
            [0.10, 0.76, 0.14],
            [0.08, 0.70, 0.22],
            [0.06, 0.14, 0.80],
            [0.12, 0.16, 0.72],
            [0.58, 0.24, 0.18],
            [0.18, 0.56, 0.26],
            [0.20, 0.22, 0.58],
        ],
        dtype=np.float64,
    )


def _sample_labels() -> np.ndarray:
    return np.array([-1, -1, 0, 0, 1, 1, -1, 0, 1], dtype=np.int64)


def test_compute_calibration_metrics_preserves_class_order() -> None:
    metrics = compute_calibration_metrics(_sample_labels(), _sample_probabilities())

    assert metrics["class_labels"] == CLASS_LABELS
    assert set(metrics["brier_by_class"].keys()) == set(CLASS_LABELS)
    assert metrics["sample_count"] == 9


def test_fit_and_apply_calibrator_returns_normalized_probabilities() -> None:
    calibrator = fit_calibrator(
        _sample_probabilities(),
        _sample_labels(),
        model_name="xgboost",
        min_samples=6,
    )

    calibrated = apply_calibrator(calibrator, _sample_probabilities())

    assert calibrator.class_labels == tuple(CLASS_LABELS)
    assert calibrated.shape == (9, 3)
    assert np.allclose(calibrated.sum(axis=1), 1.0)
    assert np.all(calibrated >= 0.0)


def test_load_calibrator_round_trip(tmp_path) -> None:
    calibrator = fit_calibrator(
        _sample_probabilities(),
        _sample_labels(),
        model_name="lightgbm",
        min_samples=6,
    )
    path = tmp_path / "lightgbm_calibrator.pkl"
    joblib.dump(calibrator, path)

    loaded = load_calibrator(str(path))
    calibrated = apply_calibrator(loaded, _sample_probabilities())

    assert loaded.model_name == "lightgbm"
    assert loaded.class_labels == tuple(CLASS_LABELS)
    assert np.allclose(calibrated.sum(axis=1), 1.0)
