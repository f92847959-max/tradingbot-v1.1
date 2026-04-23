"""Typed runtime contracts for governance decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateDecision(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    WEAKEN = "weaken"
    VETO = "veto"


@dataclass(frozen=True)
class SpecialistSignal:
    name: str
    action: str
    confidence: float
    reason: str = ""


@dataclass
class DecisionAudit:
    preliminary_action: str
    final_action: str
    regime: str
    gate_decision: GateDecision
    gate_reasons: list[str] = field(default_factory=list)
    threshold_source: str = "defaults"
    threshold_confidence: float = 0.0
    threshold_margin: float = 0.0
    conflict_ratio: float = 0.0
    confidence_before: float = 0.0
    final_confidence: float = 0.0
    global_score: float = 0.0
    specialist_effect: str | None = None
    specialist_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preliminary_action": self.preliminary_action,
            "final_action": self.final_action,
            "regime": self.regime,
            "gate_decision": self.gate_decision.value,
            "gate_reasons": list(self.gate_reasons),
            "threshold_source": self.threshold_source,
            "threshold_confidence": float(self.threshold_confidence),
            "threshold_margin": float(self.threshold_margin),
            "conflict_ratio": float(self.conflict_ratio),
            "confidence_before": float(self.confidence_before),
            "final_confidence": float(self.final_confidence),
            "global_score": float(self.global_score),
            "specialist_effect": self.specialist_effect,
            "specialist_name": self.specialist_name,
        }
