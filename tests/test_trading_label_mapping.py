"""Regression tests for label-space handling in trading evaluation/backtester."""

from __future__ import annotations

import numpy as np

from ai_engine.training.backtester import Backtester
from ai_engine.training.evaluation import ModelEvaluator


def test_evaluate_trading_signal_space_hold_only_has_no_trades() -> None:
    evaluator = ModelEvaluator()
    y_true = np.array([0, 0, 1, -1, 0], dtype=int)
    y_pred = np.array([0, 0, 0, 0, 0], dtype=int)

    out = evaluator.evaluate_trading(y_true, y_pred, label_space="signal", model_name="test")
    assert out["n_trades"] == 0
    assert out["buy_signals"] == 0
    assert out["sell_signals"] == 0


def test_evaluate_trading_class_space_hold_only_has_no_trades() -> None:
    evaluator = ModelEvaluator()
    # class-space labels: SELL=0, HOLD=1, BUY=2
    y_true = np.array([1, 1, 2, 0, 1], dtype=int)
    y_pred = np.array([1, 1, 1, 1, 1], dtype=int)

    out = evaluator.evaluate_trading(y_true, y_pred, label_space="class", model_name="test")
    assert out["n_trades"] == 0


def test_backtester_run_simple_hold_only_has_no_trades() -> None:
    bt = Backtester(initial_balance=10000.0)
    preds = np.zeros(12, dtype=int)
    truths = np.zeros(12, dtype=int)
    out = bt.run_simple(preds, truths)

    assert out["n_trades"] == 0
    assert out["final_balance"] == 10000.0
