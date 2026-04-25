"""Tests for Exit-AI calibration and promotion gates."""

from __future__ import annotations

from ai_engine.training.exit_ai_evaluation import (
    build_exit_ai_promotion_artifact,
    evaluate_exit_ai_candidate,
)


def _comparison_report(
    *,
    hold_rate: float = 0.40,
    profit_factor_delta: float = 0.10,
    calibration_score: float = 0.62,
    drawdown_proxy: float = 0.15,
) -> dict:
    baseline = {
        "profit_factor_proxy": 1.10,
        "max_drawdown_proxy": 0.20,
        "trade_retention": 0.70,
        "hold_rate": 0.45,
        "non_hold_rate": 0.55,
        "calibration_score": 0.58,
    }
    candidate = {
        "profit_factor_proxy": baseline["profit_factor_proxy"] + profit_factor_delta,
        "max_drawdown_proxy": drawdown_proxy,
        "trade_retention": 0.65,
        "hold_rate": hold_rate,
        "non_hold_rate": 1.0 - hold_rate,
        "calibration_score": calibration_score,
    }
    return {
        "comparison": {
            "baseline": baseline,
            "exit_ai_candidate": candidate,
        },
        "deltas": {
            "profit_factor_delta": profit_factor_delta,
            "drawdown_delta": baseline["max_drawdown_proxy"] - drawdown_proxy,
            "calibration_delta": calibration_score - baseline["calibration_score"],
            "trade_retention_delta": candidate["trade_retention"] - baseline["trade_retention"],
        },
    }


def test_evaluate_exit_ai_candidate_accepts_strong_candidate() -> None:
    evaluation = evaluate_exit_ai_candidate(_comparison_report())
    assert evaluation["passed"] is True
    assert evaluation["reasons"] == []


def test_evaluate_exit_ai_candidate_rejects_hold_dominant_candidate() -> None:
    evaluation = evaluate_exit_ai_candidate(_comparison_report(hold_rate=0.92))
    assert evaluation["passed"] is False
    assert evaluation["hold_collapse_detected"] is True


def test_evaluate_exit_ai_candidate_rejects_poor_calibration() -> None:
    evaluation = evaluate_exit_ai_candidate(_comparison_report(calibration_score=0.20))
    assert evaluation["passed"] is False
    assert any("Calibration" in reason for reason in evaluation["reasons"])


def test_build_exit_ai_promotion_artifact_is_serializable() -> None:
    report = _comparison_report()
    evaluation = evaluate_exit_ai_candidate(report)
    artifact = build_exit_ai_promotion_artifact(
        report,
        evaluation,
        version_dir="ai_engine/saved_models/specialists/exit_ai/v001",
    )

    assert artifact["schema_version"] == 1
    assert artifact["promotion_status"] == "approved"
    assert artifact["version_dir"].endswith("exit_ai/v001")
