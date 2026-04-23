"""Tests for calibrated champion/challenger promotion and retraining logic."""

from ai_engine.governance.promotion import (
    evaluate_candidate_promotion,
    evaluate_retraining_trigger,
)
from monitoring.model_monitor import ModelMonitor


def test_candidate_promotion_requires_min_trade_count():
    result = evaluate_candidate_promotion(
        {
            "trade_count": 120,
            "brier_score": 0.19,
            "log_loss": 0.42,
            "profit_factor": 1.30,
            "max_drawdown_pct": 0.08,
        },
        {
            "trade_count": 18,
            "brier_score": 0.15,
            "log_loss": 0.38,
            "profit_factor": 1.45,
            "max_drawdown_pct": 0.06,
        },
        min_trade_count=40,
    )

    assert result["promote"] is False
    assert any("trade_count" in reason for reason in result["reasons"])


def test_candidate_promotion_blocks_calibration_regression():
    result = evaluate_candidate_promotion(
        {
            "trade_count": 140,
            "brier_score": 0.18,
            "log_loss": 0.39,
            "profit_factor": 1.25,
            "max_drawdown_pct": 0.07,
        },
        {
            "trade_count": 140,
            "brier_score": 0.24,
            "log_loss": 0.45,
            "profit_factor": 1.35,
            "max_drawdown_pct": 0.07,
        },
    )

    assert result["promote"] is False
    assert any("brier_score regression" in reason for reason in result["reasons"])
    assert any("log_loss regression" in reason for reason in result["reasons"])


def test_candidate_promotion_accepts_better_candidate_with_safe_drawdown():
    result = evaluate_candidate_promotion(
        {
            "trade_count": 180,
            "brier_score": 0.19,
            "log_loss": 0.41,
            "profit_factor": 1.20,
            "max_drawdown_pct": 0.09,
        },
        {
            "artifact_version": "C:/models/v003_20260423",
            "trade_count": 180,
            "brier_score": 0.15,
            "log_loss": 0.34,
            "profit_factor": 1.42,
            "max_drawdown_pct": 0.08,
        },
        min_trade_count=100,
        min_profit_factor_delta=0.05,
    )

    assert result["promote"] is True
    assert result["artifact_version"] == "v003_20260423"
    assert result["deltas"]["profit_factor"] > 0


def test_retraining_trigger_requires_sustained_calibrated_degradation():
    result = evaluate_retraining_trigger(
        {
            "trade_count": 80,
            "avg_confidence": 0.49,
            "win_rate": 0.41,
            "mean_brier_score": 0.31,
            "profit_factor": 0.82,
            "max_drawdown_pct": 0.16,
            "degradation_streak": 4,
        },
        min_trade_count=50,
        max_brier_score=0.24,
        max_drawdown_pct=0.10,
        min_degradation_streak=3,
    )

    assert result["trigger_retraining"] is True
    assert any("mean_brier_score" in reason for reason in result["reasons"])
    assert any("win_rate" in reason for reason in result["reasons"])


def test_model_monitor_uses_calibrated_metrics_for_retraining():
    monitor = ModelMonitor(
        window_size=10,
        min_confidence_threshold=0.55,
        min_win_rate_threshold=0.50,
        min_trades_for_alert=3,
        max_brier_score=0.24,
        min_profit_factor=1.0,
        max_drawdown_pct=0.10,
        min_degradation_streak=2,
    )

    for _ in range(3):
        monitor.record_prediction(
            "BUY",
            0.52,
            threshold_source="ranging:BUY",
            artifact_version="v005_20260423",
        )
        monitor.record_outcome(-10.0, brier_score=0.28, drawdown_pct=0.12)

    status = monitor.status()

    assert status["avg_brier_score"] > 0.24
    assert status["max_drawdown_pct"] == 0.12
    assert status["retraining_recommended"] is True
