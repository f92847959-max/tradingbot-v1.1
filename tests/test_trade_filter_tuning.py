from __future__ import annotations

import numpy as np

from ai_engine.training.trade_filter import probs_to_trade_signals, tune_trade_filter
from ai_engine.training.trainer import ModelTrainer


def test_probs_to_trade_signals_applies_confidence_and_margin() -> None:
    y_probs = np.array(
        [
            [0.80, 0.10, 0.10],  # SELL strong
            [0.20, 0.15, 0.65],  # BUY strong
            [0.36, 0.34, 0.30],  # SELL weak (margin too low)
            [0.10, 0.75, 0.15],  # HOLD
        ],
        dtype=float,
    )

    signals = probs_to_trade_signals(
        y_probs,
        min_confidence=0.50,
        min_margin=0.05,
    )

    assert signals.tolist() == [-1, 1, 0, 0]


def test_trade_filter_tuning_prefers_higher_quality_trades(tmp_path) -> None:
    trainer = ModelTrainer(saved_models_dir=str(tmp_path))

    strong_probs: list[list[float]] = []
    strong_labels: list[int] = []
    for i in range(8):
        if i % 2 == 0:
            strong_probs.append([0.90, 0.05, 0.05])  # SELL
            strong_labels.append(-1)
        else:
            strong_probs.append([0.05, 0.05, 0.90])  # BUY
            strong_labels.append(1)

    weak_probs: list[list[float]] = []
    weak_labels: list[int] = []
    for i in range(32):
        if i % 2 == 0:
            weak_probs.append([0.36, 0.34, 0.30])  # weak SELL
        else:
            weak_probs.append([0.30, 0.34, 0.36])  # weak BUY
        weak_labels.append(0)  # HOLD -> wrong if traded

    y_probs_val = np.array(strong_probs + weak_probs, dtype=float)
    y_true_val = np.array(strong_labels + weak_labels, dtype=int)

    tuned = tune_trade_filter(
        y_true_val=y_true_val,
        y_probs_val=y_probs_val,
        model_name="XGBoost",
        evaluator=trainer._evaluator,
        tp_pips=trainer.tp_pips,
        sl_pips=trainer.sl_pips,
        spread_pips=trainer.spread_pips,
    )

    val_metrics = tuned["validation_trading"]
    assert val_metrics["n_trades"] >= tuned["min_trades_target"]
    assert val_metrics["wins"] > val_metrics["losses"]
    assert (tuned["min_confidence"] > 0.34) or (tuned["min_margin"] > 0.0)
