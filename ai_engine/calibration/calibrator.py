"""Probability calibration helpers for multi-class model outputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
from sklearn.isotonic import IsotonicRegression

from .artifacts import CLASS_LABELS


def _ensure_class_labels(y_true: np.ndarray) -> np.ndarray:
    labels = np.asarray(y_true, dtype=np.int64)
    if labels.size == 0:
        raise ValueError("y_true must not be empty")
    if labels.min() < 0:
        labels = labels + 1
    if labels.min() < 0 or labels.max() > 2:
        raise ValueError("y_true must be in signal-space [-1, 0, 1] or class-space [0, 1, 2]")
    return labels


def _ensure_probabilities(y_probs: np.ndarray) -> np.ndarray:
    probs = np.asarray(y_probs, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[1] != 3:
        raise ValueError("y_probs must have shape [n_samples, 3]")
    row_sums = probs.sum(axis=1, keepdims=True)
    safe_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return np.clip(probs / safe_sums, 1e-9, 1.0)


@dataclass
class ProbabilityCalibrator:
    """Serializable per-class isotonic calibrator bundle."""

    class_labels: tuple[str, str, str]
    calibrators: list[IsotonicRegression | None]
    class_support: dict[str, int]
    method: str = "isotonic"
    model_name: str = "model"


def fit_calibrator(
    y_probs: np.ndarray,
    y_true: np.ndarray,
    *,
    model_name: str = "model",
    min_samples: int = 20,
) -> ProbabilityCalibrator:
    probs = _ensure_probabilities(y_probs)
    labels = _ensure_class_labels(y_true)

    calibrators: list[IsotonicRegression | None] = []
    class_support: dict[str, int] = {}

    for class_idx, label_name in enumerate(CLASS_LABELS):
        targets = (labels == class_idx).astype(int)
        positives = int(targets.sum())
        negatives = int(len(targets) - positives)
        class_support[label_name] = positives

        if positives < 2 or negatives < 2 or len(targets) < int(min_samples):
            calibrators.append(None)
            continue

        calibrator = IsotonicRegression(
            out_of_bounds="clip",
            y_min=0.0,
            y_max=1.0,
        )
        calibrator.fit(probs[:, class_idx], targets)
        calibrators.append(calibrator)

    return ProbabilityCalibrator(
        class_labels=tuple(CLASS_LABELS),
        calibrators=calibrators,
        class_support=class_support,
        method="isotonic",
        model_name=model_name,
    )


def apply_calibrator(
    calibrator: ProbabilityCalibrator | None,
    y_probs: np.ndarray,
) -> np.ndarray:
    probs = _ensure_probabilities(y_probs)
    if calibrator is None:
        return probs

    calibrated = np.zeros_like(probs, dtype=np.float64)
    for class_idx, regressor in enumerate(calibrator.calibrators):
        if regressor is None:
            calibrated[:, class_idx] = probs[:, class_idx]
        else:
            calibrated[:, class_idx] = regressor.transform(probs[:, class_idx])

    calibrated = np.clip(calibrated, 1e-9, 1.0)
    row_sums = calibrated.sum(axis=1, keepdims=True)
    invalid_rows = row_sums.squeeze(axis=1) <= 0
    if np.any(invalid_rows):
        calibrated[invalid_rows] = np.array([1.0 / 3.0] * 3, dtype=np.float64)
        row_sums = calibrated.sum(axis=1, keepdims=True)
    return calibrated / row_sums


def save_calibrator(calibrator: ProbabilityCalibrator, path: str) -> str:
    joblib.dump(calibrator, path)
    return path


def load_calibrator(path: str) -> ProbabilityCalibrator:
    loaded = joblib.load(path)
    if not isinstance(loaded, ProbabilityCalibrator):
        raise TypeError("Loaded object is not a ProbabilityCalibrator")
    return loaded
