"""Promotion-gate helpers for Exit-AI candidates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def evaluate_exit_ai_candidate(
    comparison_report: dict[str, Any],
    *,
    max_hold_rate: float = 0.80,
    min_trade_retention: float = 0.30,
    min_profit_factor_delta: float = -0.05,
    min_calibration_score: float = 0.45,
    max_drawdown_regression: float = 0.05,
) -> dict[str, Any]:
    """Evaluate whether an Exit-AI candidate is promotable."""
    baseline = comparison_report["comparison"]["baseline"]
    candidate = comparison_report["comparison"]["exit_ai_candidate"]
    deltas = comparison_report.get("deltas", {})

    reasons: list[str] = []
    hold_collapse = (
        candidate.get("hold_rate", 1.0) > max_hold_rate
        or candidate.get("non_hold_rate", 0.0) < (1.0 - max_hold_rate)
    )
    if hold_collapse:
        reasons.append("Candidate collapsed into HOLD-dominant behavior")
    if candidate.get("trade_retention", 0.0) < min_trade_retention:
        reasons.append("Trade retention fell below the minimum threshold")
    if deltas.get("profit_factor_delta", -1.0) < min_profit_factor_delta:
        reasons.append("Profit-factor proxy regressed versus baseline")
    if (
        candidate.get("max_drawdown_proxy", 1.0)
        > baseline.get("max_drawdown_proxy", 0.0) + max_drawdown_regression
    ):
        reasons.append("Drawdown proxy worsened beyond the allowed buffer")
    if candidate.get("calibration_score", 0.0) < min_calibration_score:
        reasons.append("Calibration score fell below the minimum threshold")

    passed = not reasons
    return {
        "schema_version": 1,
        "artifact_type": "exit_ai_promotion_evaluation",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "hold_collapse_detected": hold_collapse,
        "reasons": reasons,
        "thresholds": {
            "max_hold_rate": float(max_hold_rate),
            "min_trade_retention": float(min_trade_retention),
            "min_profit_factor_delta": float(min_profit_factor_delta),
            "min_calibration_score": float(min_calibration_score),
            "max_drawdown_regression": float(max_drawdown_regression),
        },
        "baseline_metrics": baseline,
        "candidate_metrics": candidate,
        "comparison_deltas": deltas,
    }


def build_exit_ai_promotion_artifact(
    comparison_report: dict[str, Any],
    evaluation: dict[str, Any],
    *,
    version_dir: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable promotion artifact."""
    return {
        "schema_version": 1,
        "artifact_type": "exit_ai_promotion_artifact",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "promotion_status": "approved" if evaluation["passed"] else "rejected",
        "version_dir": version_dir,
        "comparison_report": comparison_report,
        "evaluation": evaluation,
    }
