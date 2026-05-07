"""Regression tests for estimator class-probability alignment."""

import numpy as np

from ai_engine.models.base_model import BaseModel


def test_align_class_probabilities_uses_estimator_classes_not_positions() -> None:
    probs = np.array([[0.25, 0.75]], dtype=float)
    aligned = BaseModel._align_class_probabilities(probs, classes=np.array([1, 2]))

    assert aligned.shape == (1, 3)
    assert aligned[0, 0] == 0.0
    assert aligned[0, 1] == 0.25
    assert aligned[0, 2] == 0.75
    assert aligned.sum(axis=1)[0] == 1.0


def test_align_class_probabilities_fills_invalid_empty_rows_as_hold() -> None:
    probs = np.array([[0.0, 0.0]], dtype=float)
    aligned = BaseModel._align_class_probabilities(probs, classes=np.array([0, 2]))

    assert np.allclose(aligned, np.array([[0.0, 1.0, 0.0]]))
