"""Champion/challenger and retraining helpers for calibrated governance."""

from __future__ import annotations

import os
from typing import Any


def _as_float(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = metrics.get(key, default)
    if value is None:
        return default
    return float(value)


def _as_int(metrics: dict[str, Any], key: str, default: int = 0) -> int:
    value = metrics.get(key, default)
    if value is None:
        return default
    return int(value)


def _sanitize_artifact_version(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).replace("\\", "/").rstrip("/")
    candidate = os.path.basename(normalized)
    if not candidate or candidate in {".", ".."}:
        return None
    return candidate[:120]


def evaluate_candidate_promotion(
    champion_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    *,
    min_trade_count: int = 50,
    max_brier_regression: float = 0.0,
    max_log_loss_regression: float = 0.0,
    min_profit_factor_delta: float = 0.0,
    max_drawdown_increase: float = 0.02,
) -> dict[str, Any]:
    """Compare a challenger against the champion using calibrated metrics."""
    reasons: list[str] = []
    candidate_trades = _as_int(candidate_metrics, "trade_count")
    if candidate_trades < min_trade_count:
        reasons.append(
            f"trade_count {candidate_trades} < min_trade_count {min_trade_count}"
        )

    champion_brier = _as_float(champion_metrics, "brier_score")
    candidate_brier = _as_float(candidate_metrics, "brier_score")
    champion_log_loss = _as_float(champion_metrics, "log_loss")
    candidate_log_loss = _as_float(candidate_metrics, "log_loss")
    champion_pf = _as_float(champion_metrics, "profit_factor")
    candidate_pf = _as_float(candidate_metrics, "profit_factor")
    champion_drawdown = _as_float(champion_metrics, "max_drawdown_pct")
    candidate_drawdown = _as_float(candidate_metrics, "max_drawdown_pct")

    if candidate_brier > champion_brier + max_brier_regression:
        reasons.append(
            f"brier_score regression {candidate_brier:.4f} > {champion_brier + max_brier_regression:.4f}"
        )
    if candidate_log_loss > champion_log_loss + max_log_loss_regression:
        reasons.append(
            f"log_loss regression {candidate_log_loss:.4f} > {champion_log_loss + max_log_loss_regression:.4f}"
        )
    if candidate_pf < champion_pf + min_profit_factor_delta:
        reasons.append(
            f"profit_factor {candidate_pf:.4f} < required {champion_pf + min_profit_factor_delta:.4f}"
        )
    if candidate_drawdown > champion_drawdown + max_drawdown_increase:
        reasons.append(
            f"max_drawdown_pct {candidate_drawdown:.4f} > allowed {champion_drawdown + max_drawdown_increase:.4f}"
        )

    return {
        "promote": not reasons,
        "reasons": reasons,
        "artifact_version": _sanitize_artifact_version(
            candidate_metrics.get("artifact_version")
        ),
        "candidate_trade_count": candidate_trades,
        "metrics": {
            "candidate": {
                "brier_score": candidate_brier,
                "log_loss": candidate_log_loss,
                "profit_factor": candidate_pf,
                "max_drawdown_pct": candidate_drawdown,
            },
            "champion": {
                "brier_score": champion_brier,
                "log_loss": champion_log_loss,
                "profit_factor": champion_pf,
                "max_drawdown_pct": champion_drawdown,
            },
        },
        "deltas": {
            "brier_score": round(candidate_brier - champion_brier, 6),
            "log_loss": round(candidate_log_loss - champion_log_loss, 6),
            "profit_factor": round(candidate_pf - champion_pf, 6),
            "max_drawdown_pct": round(candidate_drawdown - champion_drawdown, 6),
        },
    }


def evaluate_retraining_trigger(
    metrics: dict[str, Any],
    *,
    min_trade_count: int = 50,
    confidence_floor: float = 0.55,
    min_win_rate: float = 0.50,
    max_brier_score: float = 0.24,
    min_profit_factor: float = 1.0,
    max_drawdown_pct: float = 0.12,
    min_degradation_streak: int = 3,
) -> dict[str, Any]:
    """Decide if retraining should trigger from calibrated degradation evidence."""
    reasons: list[str] = []
    trade_count = _as_int(metrics, "trade_count")
    avg_confidence = _as_float(metrics, "avg_confidence")
    win_rate = _as_float(metrics, "win_rate")
    mean_brier_score = _as_float(metrics, "mean_brier_score")
    profit_factor = _as_float(metrics, "profit_factor")
    drawdown = _as_float(metrics, "max_drawdown_pct")
    degradation_streak = _as_int(metrics, "degradation_streak")

    if trade_count < min_trade_count:
        return {
            "trigger_retraining": False,
            "reasons": [f"trade_count {trade_count} < min_trade_count {min_trade_count}"],
            "metrics": {
                "trade_count": trade_count,
                "avg_confidence": avg_confidence,
                "win_rate": win_rate,
                "mean_brier_score": mean_brier_score,
                "profit_factor": profit_factor,
                "max_drawdown_pct": drawdown,
                "degradation_streak": degradation_streak,
            },
        }

    if avg_confidence < confidence_floor:
        reasons.append(
            f"avg_confidence {avg_confidence:.4f} < floor {confidence_floor:.4f}"
        )
    if mean_brier_score > max_brier_score:
        reasons.append(
            f"mean_brier_score {mean_brier_score:.4f} > max {max_brier_score:.4f}"
        )
    if win_rate < min_win_rate:
        reasons.append(f"win_rate {win_rate:.4f} < min {min_win_rate:.4f}")
    if profit_factor < min_profit_factor:
        reasons.append(
            f"profit_factor {profit_factor:.4f} < min {min_profit_factor:.4f}"
        )
    if drawdown > max_drawdown_pct:
        reasons.append(
            f"max_drawdown_pct {drawdown:.4f} > max {max_drawdown_pct:.4f}"
        )
    if degradation_streak < min_degradation_streak:
        reasons.append(
            f"degradation_streak {degradation_streak} < min {min_degradation_streak}"
        )

    hard_failures = sum(
        1
        for value in (
            mean_brier_score > max_brier_score,
            win_rate < min_win_rate,
            drawdown > max_drawdown_pct,
        )
        if value
    )
    trigger = degradation_streak >= min_degradation_streak and hard_failures >= 2

    return {
        "trigger_retraining": trigger,
        "reasons": reasons,
        "metrics": {
            "trade_count": trade_count,
            "avg_confidence": avg_confidence,
            "win_rate": win_rate,
            "mean_brier_score": mean_brier_score,
            "profit_factor": profit_factor,
            "max_drawdown_pct": drawdown,
            "degradation_streak": degradation_streak,
        },
    }
