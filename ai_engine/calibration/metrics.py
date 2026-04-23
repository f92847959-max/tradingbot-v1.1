"""Calibration metric helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import log_loss

from .artifacts import CLASS_LABELS


def _ensure_class_labels(y_true: np.ndarray) -> np.ndarray:
    labels = np.asarray(y_true, dtype=np.int64)
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


def compute_calibration_metrics(
    y_true: np.ndarray,
    y_probs: np.ndarray,
    *,
    bins: int = 10,
) -> dict[str, Any]:
    labels = _ensure_class_labels(y_true)
    probs = _ensure_probabilities(y_probs)

    one_hot = np.eye(3, dtype=np.float64)[labels]
    brier_per_class = np.mean((probs - one_hot) ** 2, axis=0)
    brier_score = float(np.mean(np.sum((probs - one_hot) ** 2, axis=1)))
    mlog_loss = float(log_loss(labels, probs, labels=[0, 1, 2]))

    confidences = probs.max(axis=1)
    predictions = probs.argmax(axis=1)
    correctness = (predictions == labels).astype(np.float64)

    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    expected_calibration_error = 0.0
    reliability_bins = []
    for idx in range(bins):
        lower = bin_edges[idx]
        upper = bin_edges[idx + 1]
        if idx == bins - 1:
            mask = (confidences >= lower) & (confidences <= upper)
        else:
            mask = (confidences >= lower) & (confidences < upper)

        count = int(mask.sum())
        if count == 0:
            continue

        avg_confidence = float(confidences[mask].mean())
        accuracy = float(correctness[mask].mean())
        expected_calibration_error += (count / len(confidences)) * abs(
            avg_confidence - accuracy
        )
        reliability_bins.append(
            {
                "bin": idx,
                "count": count,
                "avg_confidence": avg_confidence,
                "accuracy": accuracy,
            }
        )

    return {
        "class_labels": list(CLASS_LABELS),
        "log_loss": mlog_loss,
        "brier_score": brier_score,
        "brier_by_class": {
            label: float(score)
            for label, score in zip(CLASS_LABELS, brier_per_class)
        },
        "expected_calibration_error": float(expected_calibration_error),
        "avg_confidence": float(confidences.mean()),
        "avg_correctness": float(correctness.mean()),
        "reliability_bins": reliability_bins,
        "sample_count": int(len(labels)),
    }
