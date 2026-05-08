"""Promotion gate and shadow-training manifest helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromotionGateConfig:
    min_candidate_profit_factor: float = 1.20
    min_pf_uplift_ratio: float = 1.05
    max_drawdown_worsening_ratio: float = 1.10
    max_calibration_error: float = 0.08
    min_confidence_bucket_support: int = 20
    min_non_hold_trades: int = 20


def evaluate_training_promotion(
    candidate_report: dict[str, Any],
    champion_report: dict[str, Any],
    *,
    config: PromotionGateConfig | None = None,
) -> dict[str, Any]:
    """Evaluate candidate training metrics against the current champion."""
    cfg = config or PromotionGateConfig()
    candidate = _extract_metrics(candidate_report)
    champion = _extract_metrics(champion_report)

    reasons: list[str] = []
    for missing in candidate.get("missing_metrics", []):
        reasons.append(f"candidate_missing_{missing}")
    for missing in champion.get("missing_metrics", []):
        reasons.append(f"champion_missing_{missing}")

    candidate_pf = candidate["profit_factor"]
    champion_pf = champion["profit_factor"]
    pf_uplift_ratio = candidate_pf / champion_pf if champion_pf > 0 else float("inf")

    if candidate_pf < cfg.min_candidate_profit_factor:
        reasons.append("candidate_profit_factor_below_minimum")
    if pf_uplift_ratio < cfg.min_pf_uplift_ratio:
        reasons.append("profit_factor_uplift_below_required_ratio")

    candidate_drawdown = candidate["max_drawdown"]
    champion_drawdown = champion["max_drawdown"]
    drawdown_limit = champion_drawdown * cfg.max_drawdown_worsening_ratio
    if champion_drawdown > 0 and candidate_drawdown > drawdown_limit:
        reasons.append("drawdown_worse_than_allowed")

    calibration_error = candidate["calibration_error"]
    if calibration_error > cfg.max_calibration_error:
        reasons.append("calibration_error_above_limit")

    min_bucket_support = candidate["min_confidence_bucket_support"]
    if min_bucket_support < cfg.min_confidence_bucket_support:
        reasons.append("confidence_bucket_support_below_minimum")

    non_hold_trades = candidate["non_hold_trades"]
    if non_hold_trades < cfg.min_non_hold_trades:
        reasons.append("non_hold_trade_count_below_minimum")

    candidate_windows = _windows(candidate_report)
    champion_windows = _windows(champion_report)
    if not candidate_windows or not champion_windows:
        reasons.append("walk_forward_windows_missing")
    elif candidate_windows != champion_windows:
        reasons.append("walk_forward_windows_do_not_match")

    approved = not reasons
    return {
        "approved": approved,
        "mode": "shadow_ready" if approved else "blocked",
        "reasons": reasons,
        "gate_metrics": {
            "candidate_profit_factor": candidate_pf,
            "champion_profit_factor": champion_pf,
            "pf_uplift_ratio": pf_uplift_ratio,
            "candidate_max_drawdown": candidate_drawdown,
            "champion_max_drawdown": champion_drawdown,
            "calibration_error": calibration_error,
            "min_confidence_bucket_support": min_bucket_support,
            "non_hold_trades": non_hold_trades,
        },
        "candidate_version": candidate_report.get("version", "candidate"),
        "champion_version": champion_report.get("version", "champion"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def write_promotion_decision(decision: dict[str, Any], path: str | Path) -> str:
    """Write a promotion decision as JSON and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(decision, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)


def build_shadow_training_manifest(
    decision: dict[str, Any],
    dataset_manifest: dict[str, Any],
    split_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Build a shadow-training manifest without changing runtime pointers."""
    return {
        "schema_version": 1,
        "mode": "shadow_training",
        "approved": bool(decision.get("approved")),
        "candidate_version": decision.get("candidate_version"),
        "champion_version": decision.get("champion_version"),
        "decision": decision,
        "dataset_manifest": dataset_manifest,
        "split_manifest": split_manifest,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _extract_metrics(report: dict[str, Any]) -> dict[str, Any]:
    aggregate = report.get("aggregate") or report.get("aggregate_metrics", {})
    best_model = aggregate.get("best_model") or _choose_best_model(aggregate)
    model_metrics = aggregate.get(best_model, {}) if best_model else {}
    gate_metrics = report.get("gate_metrics") or report.get(
        "promotion_decision", {},
    ).get("gate_metrics", {})
    confidence_buckets = report.get("confidence_buckets", {})

    bucket_support = [
        int(bucket.get("support", 0))
        for bucket in confidence_buckets.values()
        if bucket.get("actionable", True)
    ]
    if not bucket_support and "confidence_bucket_support" in gate_metrics:
        value = gate_metrics["confidence_bucket_support"]
        if isinstance(value, dict):
            bucket_support = [int(v) for v in value.values()]
        else:
            bucket_support = [int(value)]

    missing_metrics: list[str] = []

    profit_factor = _lookup_metric(
        "profit_factor",
        gate_metrics,
        report,
        model_metrics,
        aliases=("profit_factor",),
        missing_metrics=missing_metrics,
    )
    max_drawdown = _lookup_metric(
        "max_drawdown",
        gate_metrics,
        report,
        model_metrics,
        aliases=("max_drawdown", "max_drawdown_pct", "max_drawdown_pcts"),
        missing_metrics=missing_metrics,
    )
    calibration_error = _lookup_metric(
        "calibration_error",
        gate_metrics,
        report,
        model_metrics,
        aliases=("calibration_error", "expected_calibration_error"),
        missing_metrics=missing_metrics,
    )

    return {
        "profit_factor": float(profit_factor),
        "max_drawdown": float(max_drawdown),
        "calibration_error": float(calibration_error),
        "min_confidence_bucket_support": min(bucket_support) if bucket_support else 0,
        "non_hold_trades": int(
            gate_metrics.get(
                "non_hold_trades",
                report.get("non_hold_trades", model_metrics.get("n_trades", 0)),
            )
        ),
        "missing_metrics": missing_metrics,
    }


def _lookup_metric(
    metric_name: str,
    gate_metrics: dict[str, Any],
    report: dict[str, Any],
    model_metrics: dict[str, Any],
    *,
    aliases: tuple[str, ...],
    missing_metrics: list[str],
) -> float:
    for source in (gate_metrics, report, model_metrics):
        for alias in aliases:
            if alias in source and source[alias] is not None:
                return float(source[alias])
    missing_metrics.append(metric_name)
    return 0.0


def _choose_best_model(aggregate: dict[str, Any]) -> str | None:
    candidates = {
        key: value.get("profit_factor", 0.0)
        for key, value in aggregate.items()
        if isinstance(value, dict)
    }
    return max(candidates, key=candidates.get) if candidates else None


def _windows(report: dict[str, Any]) -> list[Any]:
    split = report.get("split_manifest", {})
    if split.get("windows"):
        return split["windows"]
    walk_forward = report.get("walk_forward", {})
    if walk_forward.get("windows"):
        return walk_forward["windows"]
    summary = report.get("summary", {})
    if summary.get("windows"):
        return summary["windows"]
    return []
