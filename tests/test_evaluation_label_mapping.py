"""Regression tests for ML evaluation label-space mapping."""

from __future__ import annotations

import numpy as np

from ai_engine.training.evaluation import ModelEvaluator


def test_evaluate_probabilities_signal_hold_only_is_mapped_to_hold_class() -> None:
    evaluator = ModelEvaluator()
    # signal-space HOLD labels only (0), should map to class-space HOLD (1)
    y_true = np.zeros(12, dtype=int)
    y_probs = np.zeros((12, 3), dtype=float)
    y_probs[:, 1] = 1.0  # predict HOLD with certainty

    out = evaluator.evaluate_probabilities(
        y_true,
        y_probs,
        label_space="signal",
        model_name="test",
    )

    assert out["accuracy"] == 1.0
    assert out["confusion_matrix"][1][1] == 12
    assert out["confusion_matrix"][0][1] == 0


def test_evaluate_signal_space_hold_only() -> None:
    evaluator = ModelEvaluator()
    y_true = np.array([0, 0, 0, 0], dtype=int)
    y_pred = np.array([0, 0, 0, 0], dtype=int)

    out = evaluator.evaluate(y_true, y_pred, label_space="signal", model_name="test")
    assert out["accuracy"] == 1.0
    assert out["confusion_matrix"][1][1] == 4


def test_evaluate_class_space_hold_only() -> None:
    evaluator = ModelEvaluator()
    y_true = np.array([1, 1, 1], dtype=int)  # HOLD in class-space
    y_pred = np.array([1, 1, 1], dtype=int)

    out = evaluator.evaluate(y_true, y_pred, label_space="class", model_name="test")
    assert out["accuracy"] == 1.0
    assert out["confusion_matrix"][1][1] == 3

