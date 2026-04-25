"""Decision-time teacher snapshot capture for autonomy distillation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


ACTIONS: tuple[str, ...] = ("SELL", "HOLD", "BUY")
ACTION_TO_LABEL = {"SELL": 0, "HOLD": 1, "BUY": 2}
LABEL_TO_ACTION = {value: key for key, value in ACTION_TO_LABEL.items()}


@dataclass(frozen=True)
class DecisionSnapshot:
    """A causal decision-state record captured before broker side effects."""

    timestamp: str
    observation: dict[str, float]
    preliminary_action: str
    policy_action: str
    final_action: str
    block_stage: str
    block_codes: list[str]
    failed_checks: list[dict[str, Any]] = field(default_factory=list)
    teacher_outputs: dict[str, Any] = field(default_factory=dict)
    realized_outcome: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["labels"] = {
            "preliminary_label": ACTION_TO_LABEL[self.preliminary_action],
            "policy_label": ACTION_TO_LABEL[self.policy_action],
            "final_label": ACTION_TO_LABEL[self.final_action],
            "blocked": self.block_stage != "none",
        }
        return payload


def build_decision_snapshot(
    *,
    raw_signal: Mapping[str, Any],
    policy_signal: Mapping[str, Any] | None = None,
    final_signal: Mapping[str, Any] | None = None,
    block_stage: str = "none",
    block_codes: list[str] | None = None,
    risk_approval: Any | None = None,
    event_context: Mapping[str, Any] | None = None,
    strategy_context: Mapping[str, Any] | None = None,
    realized_outcome: Mapping[str, Any] | None = None,
    timestamp: str | None = None,
) -> DecisionSnapshot:
    """Build a hierarchical teacher snapshot from current runtime outputs."""
    audit = _extract_audit(raw_signal)
    preliminary_action = _coerce_action(
        audit.get("preliminary_action")
        or raw_signal.get("action")
        or "HOLD"
    )
    policy_source = policy_signal or raw_signal
    policy_action = _coerce_action(policy_source.get("action", preliminary_action))
    final_source = final_signal or policy_signal or raw_signal
    final_action = _coerce_action(final_source.get("action", policy_action))

    normalized_block_stage = str(block_stage or "none")
    normalized_block_codes = list(block_codes or [])
    failed_checks = _extract_failed_checks(risk_approval)
    if failed_checks and normalized_block_stage == "none":
        normalized_block_stage = "risk"
    if failed_checks and not normalized_block_codes:
        normalized_block_codes = [
            str(item.get("code") or item.get("name") or "RISK_CHECK_FAILED")
            for item in failed_checks
        ]

    if normalized_block_stage != "none" and final_action == "HOLD":
        # Preserve the blocked policy target; final HOLD alone is ambiguous.
        final_action = "HOLD"

    return DecisionSnapshot(
        timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
        observation=_build_observation(raw_signal),
        preliminary_action=preliminary_action,
        policy_action=policy_action,
        final_action=final_action,
        block_stage=normalized_block_stage,
        block_codes=normalized_block_codes,
        failed_checks=failed_checks,
        teacher_outputs={
            "ensemble": _compact_signal(raw_signal),
            "policy": _compact_signal(policy_source),
            "final": _compact_signal(final_source),
            "event": dict(event_context or {}),
            "strategy": dict(strategy_context or {}),
            "risk": _risk_summary(risk_approval),
        },
        realized_outcome=dict(realized_outcome or {}),
    )


def _extract_audit(signal: Mapping[str, Any]) -> dict[str, Any]:
    final_aggregation = signal.get("final_aggregation") or {}
    audit = final_aggregation.get("decision_audit") or signal.get("decision_audit") or {}
    return dict(audit)


def _build_observation(signal: Mapping[str, Any]) -> dict[str, float]:
    final_aggregation = signal.get("final_aggregation") or {}
    probabilities = signal.get("ensemble_probabilities") or {}
    return {
        "confidence": _float(signal.get("confidence")),
        "trade_score": _float(signal.get("trade_score")),
        "entry_price": _float(signal.get("entry_price")),
        "stop_loss": _float(signal.get("stop_loss")),
        "take_profit": _float(signal.get("take_profit")),
        "risk_reward_ratio": _float(signal.get("risk_reward_ratio")),
        "global_score": _float(final_aggregation.get("global_score")),
        "conflict_ratio": _float(final_aggregation.get("conflict_ratio")),
        "prob_sell": _float(probabilities.get("SELL")),
        "prob_hold": _float(probabilities.get("HOLD"), 1.0),
        "prob_buy": _float(probabilities.get("BUY")),
    }


def _compact_signal(signal: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "action": _coerce_action(signal.get("action", "HOLD")),
        "confidence": _float(signal.get("confidence")),
        "trade_score": _float(signal.get("trade_score")),
        "reasoning": signal.get("reasoning") or [],
    }


def _risk_summary(risk_approval: Any | None) -> dict[str, Any]:
    if risk_approval is None:
        return {}
    if isinstance(risk_approval, Mapping):
        return dict(risk_approval)
    return {
        "approved": bool(getattr(risk_approval, "approved", False)),
        "reason": str(getattr(risk_approval, "reason", "")),
        "lot_size": _float(getattr(risk_approval, "lot_size", 0.0)),
        "failed_checks": _extract_failed_checks(risk_approval),
    }


def _extract_failed_checks(risk_approval: Any | None) -> list[dict[str, Any]]:
    if risk_approval is None:
        return []
    raw = None
    if isinstance(risk_approval, Mapping):
        raw = risk_approval.get("failed_checks") or risk_approval.get("failures")
    else:
        raw = getattr(risk_approval, "failed_checks", None)
    if not raw:
        return []
    result = []
    for item in raw:
        if isinstance(item, Mapping):
            result.append(dict(item))
        else:
            result.append({"code": str(item), "passed": False})
    return result


def _coerce_action(value: Any) -> str:
    action = str(value or "HOLD").upper()
    return action if action in ACTION_TO_LABEL else "HOLD"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
