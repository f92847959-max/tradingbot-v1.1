"""Focused tests for specialist-only governance guardrails."""

from ai_engine.governance.decision_governor import DecisionGovernor
from ai_engine.governance.types import GateDecision, SpecialistSignal


def _artifact() -> dict:
    return {
        "schema_version": 1,
        "class_labels": ["SELL", "HOLD", "BUY"],
        "defaults": {
            "SELL": {"action": "SELL", "min_confidence": 0.55, "min_margin": 0.03},
            "BUY": {"action": "BUY", "min_confidence": 0.55, "min_margin": 0.03},
            "HOLD": {"action": "HOLD", "min_confidence": 1.0, "min_margin": 0.0},
            "max_conflict_ratio": 0.60,
        },
        "thresholds": {
            "global": {
                "SELL": {"action": "SELL", "min_confidence": 0.55, "min_margin": 0.03},
                "BUY": {"action": "BUY", "min_confidence": 0.55, "min_margin": 0.03},
            }
        },
    }


def test_specialist_only_trade_is_rejected_when_core_is_hold() -> None:
    governor = DecisionGovernor()
    specialist = SpecialistSignal(
        name="market_structure_liquidity",
        action="BUY",
        confidence=0.90,
    )

    audit = governor.evaluate(
        preliminary_action="HOLD",
        confidence=0.20,
        global_score=0.01,
        conflict_ratio=0.0,
        regime="ranging",
        threshold_artifact=_artifact(),
        specialist_signal=specialist,
    )

    assert audit.final_action == "HOLD"
    assert audit.gate_decision is GateDecision.VETO
    assert "specialist_only_rejected" in audit.gate_reasons


def test_specialist_veto_blocks_conflicting_direction() -> None:
    governor = DecisionGovernor()
    specialist = SpecialistSignal(
        name="market_structure_liquidity",
        action="SELL",
        confidence=0.88,
    )

    audit = governor.evaluate(
        preliminary_action="BUY",
        confidence=0.72,
        global_score=0.28,
        conflict_ratio=0.05,
        regime="trending",
        threshold_artifact=_artifact(),
        specialist_signal=specialist,
    )

    assert audit.final_action == "HOLD"
    assert audit.gate_decision is GateDecision.VETO
    assert any("specialist_veto" in reason for reason in audit.gate_reasons)
