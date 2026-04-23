"""Pure policy layer for final runtime trading gates."""

from __future__ import annotations

from typing import Any

from ..calibration.artifacts import CLASS_LABELS
from ..calibration.threshold_tuner import lookup_threshold
from .types import DecisionAudit, GateDecision, SpecialistSignal


class DecisionGovernor:
    """Deterministic policy layer for pass/block/weaken/veto decisions."""

    def __init__(
        self,
        *,
        default_min_confidence: float = 0.55,
        default_min_margin: float = 0.0,
        default_max_conflict_ratio: float = 0.60,
        higher_tf_penalty: float = 0.70,
        specialist_weaken_penalty: float = 0.80,
        specialist_veto_confidence: float = 0.75,
    ) -> None:
        self.default_min_confidence = float(default_min_confidence)
        self.default_min_margin = float(default_min_margin)
        self.default_max_conflict_ratio = float(default_max_conflict_ratio)
        self.higher_tf_penalty = float(higher_tf_penalty)
        self.specialist_weaken_penalty = float(specialist_weaken_penalty)
        self.specialist_veto_confidence = float(specialist_veto_confidence)

    def build_default_threshold_artifact(self) -> dict[str, Any]:
        directional = {
            action: {
                "action": action,
                "min_confidence": self.default_min_confidence,
                "min_margin": self.default_min_margin,
            }
            for action in ("SELL", "BUY")
        }
        return {
            "schema_version": 1,
            "class_labels": list(CLASS_LABELS),
            "source": {"model_name": "runtime-default"},
            "defaults": {
                **directional,
                "HOLD": {
                    "action": "HOLD",
                    "min_confidence": 1.0,
                    "min_margin": 0.0,
                },
                "max_conflict_ratio": self.default_max_conflict_ratio,
            },
            "thresholds": {
                "global": directional,
                "ranging": directional,
            },
        }

    def evaluate(
        self,
        *,
        preliminary_action: str,
        confidence: float,
        global_score: float,
        conflict_ratio: float,
        regime: str,
        threshold_artifact: dict[str, Any] | None,
        higher_tf_aligned: bool = True,
        higher_tf_detail: str = "aligned",
        specialist_signal: SpecialistSignal | None = None,
    ) -> DecisionAudit:
        artifact = threshold_artifact or self.build_default_threshold_artifact()
        audit = DecisionAudit(
            preliminary_action=preliminary_action,
            final_action=preliminary_action,
            regime=str(regime),
            gate_decision=GateDecision.PASS,
            threshold_source="defaults",
            threshold_confidence=self.default_min_confidence,
            threshold_margin=self.default_min_margin,
            conflict_ratio=float(conflict_ratio),
            confidence_before=float(confidence),
            final_confidence=float(confidence),
            global_score=float(global_score),
        )

        threshold_info = lookup_threshold(
            artifact,
            regime=regime,
            action=preliminary_action,
        )
        audit.threshold_source = str(threshold_info.get("threshold_source", "defaults"))
        audit.threshold_confidence = float(
            threshold_info.get("min_confidence", self.default_min_confidence)
        )
        audit.threshold_margin = float(
            threshold_info.get("min_margin", self.default_min_margin)
        )

        max_conflict_ratio = float(
            artifact.get("defaults", {}).get(
                "max_conflict_ratio",
                self.default_max_conflict_ratio,
            )
        )

        if preliminary_action == "HOLD":
            if specialist_signal and specialist_signal.action != "HOLD":
                audit.gate_decision = GateDecision.VETO
                audit.gate_reasons.append("specialist_only_rejected")
                audit.specialist_effect = "specialist_only_rejected"
                audit.specialist_name = specialist_signal.name
                audit.final_confidence = 0.0
            return audit

        if conflict_ratio > max_conflict_ratio:
            audit.final_action = "HOLD"
            audit.gate_decision = GateDecision.BLOCK
            audit.final_confidence = min(audit.final_confidence, abs(global_score))
            audit.gate_reasons.append(
                f"conflict_ratio {conflict_ratio:.2f} > max {max_conflict_ratio:.2f}"
            )
            return audit

        if not higher_tf_aligned:
            audit.gate_decision = GateDecision.WEAKEN
            audit.final_confidence *= self.higher_tf_penalty
            audit.gate_reasons.append(f"higher_tf_penalty: {higher_tf_detail}")

        if specialist_signal and specialist_signal.action != "HOLD":
            audit.specialist_name = specialist_signal.name
            if specialist_signal.action == preliminary_action:
                audit.specialist_effect = "confirm"
                audit.gate_reasons.append(
                    f"specialist_confirm {specialist_signal.name}"
                )
                audit.final_confidence = max(
                    audit.final_confidence,
                    min(1.0, float(specialist_signal.confidence) * 0.90),
                )
            else:
                if specialist_signal.confidence >= self.specialist_veto_confidence:
                    audit.final_action = "HOLD"
                    audit.gate_decision = GateDecision.VETO
                    audit.final_confidence = min(
                        audit.final_confidence,
                        float(specialist_signal.confidence),
                    )
                    audit.specialist_effect = "veto"
                    audit.gate_reasons.append(
                        f"specialist_veto {specialist_signal.name}"
                    )
                    return audit

                audit.specialist_effect = "weaken"
                if audit.gate_decision is GateDecision.PASS:
                    audit.gate_decision = GateDecision.WEAKEN
                audit.final_confidence *= self.specialist_weaken_penalty
                audit.gate_reasons.append(
                    f"specialist_weaken {specialist_signal.name}"
                )

        if audit.final_confidence < audit.threshold_confidence:
            audit.final_action = "HOLD"
            if audit.gate_decision is not GateDecision.VETO:
                audit.gate_decision = GateDecision.BLOCK
            audit.gate_reasons.append(
                f"global_confidence {audit.final_confidence:.2f} < min {audit.threshold_confidence:.2f}"
            )

        return audit
