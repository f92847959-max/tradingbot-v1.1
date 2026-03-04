"""
Trade Filter -- Confidence/margin gating utilities for trade signals.

Provides functions to convert raw model probabilities into filtered
trade signals and to tune the confidence/margin thresholds on a
validation set.
"""

from typing import Any, Dict

import numpy as np

from .evaluation import ModelEvaluator


def probs_to_trade_signals(
    y_probs: np.ndarray,
    min_confidence: float,
    min_margin: float,
) -> np.ndarray:
    """Convert class probabilities [SELL, HOLD, BUY] to signal labels [-1, 0, 1]."""
    probs = np.asarray(y_probs, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[1] < 3:
        raise ValueError("y_probs must be 2D with shape [n_samples, 3].")

    class_idx = np.argmax(probs, axis=1)  # 0=SELL,1=HOLD,2=BUY
    max_prob = probs[np.arange(len(probs)), class_idx]
    second_best = np.partition(probs, -2, axis=1)[:, -2]
    margin = max_prob - second_best

    # Map class-space to signal-space: 0->-1, 1->0, 2->1
    signals = class_idx.astype(int) - 1

    # Low-confidence directional predictions are forced to HOLD.
    directional = signals != 0
    weak = (max_prob < float(min_confidence)) | (margin < float(min_margin))
    signals[directional & weak] = 0
    return signals.astype(int)


def trade_metrics_rank(
    metrics: Dict[str, Any],
    *,
    min_trades: int,
) -> tuple[float, float, float, float, float]:
    """Ranking key for trade filter tuning (higher is better)."""
    n_trades = int(metrics.get("n_trades", 0) or 0)
    win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
    profit_factor = float(metrics.get("profit_factor", 0.0) or 0.0)
    expectancy = float(metrics.get("expectancy", 0.0) or 0.0)
    total_pips = float(metrics.get("total_pips", 0.0) or 0.0)

    # Avoid runaway ranking from tiny samples with PF=inf.
    if not np.isfinite(profit_factor):
        profit_factor = 10.0

    enough_trades = 1.0 if n_trades >= min_trades else 0.0
    return (
        enough_trades,
        profit_factor,
        win_rate,
        expectancy,
        total_pips,
    )


def tune_trade_filter(
    *,
    y_true_val: np.ndarray,
    y_probs_val: np.ndarray,
    model_name: str,
    evaluator: ModelEvaluator,
    tp_pips: float,
    sl_pips: float,
    spread_pips: float,
) -> Dict[str, Any]:
    """
    Tune confidence/margin gates on validation data to avoid low-quality trades.
    """
    confidence_grid = (0.34, 0.40, 0.46, 0.52, 0.58, 0.64, 0.70)
    margin_grid = (0.00, 0.03, 0.06, 0.09, 0.12)
    min_trades = max(5, int(len(y_true_val) * 0.08))

    best: Dict[str, Any] | None = None
    best_rank: tuple[float, float, float, float, float] | None = None

    for min_conf in confidence_grid:
        for min_margin in margin_grid:
            y_pred_val = probs_to_trade_signals(
                y_probs_val,
                min_confidence=min_conf,
                min_margin=min_margin,
            )
            trading_val = evaluator.evaluate_trading(
                y_true_val,
                y_pred_val,
                tp_pips=tp_pips,
                sl_pips=sl_pips,
                spread_pips=spread_pips,
                label_space="signal",
                model_name=f"{model_name}_val_tune",
                log_details=False,
            )
            rank = trade_metrics_rank(trading_val, min_trades=min_trades)
            if best is None or best_rank is None or rank > best_rank:
                best = {
                    "min_confidence": float(min_conf),
                    "min_margin": float(min_margin),
                    "min_trades_target": int(min_trades),
                    "validation_trading": trading_val,
                }
                best_rank = rank

    assert best is not None
    return best
