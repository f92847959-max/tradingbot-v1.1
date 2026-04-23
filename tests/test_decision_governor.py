"""Focused tests for runtime decision governance."""

from ai_engine.governance.decision_governor import DecisionGovernor
from ai_engine.governance.types import GateDecision
from strategy.regime_detector import MarketRegime


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
                "SELL": {"action": "SELL", "min_confidence": 0.56, "min_margin": 0.03},
                "BUY": {"action": "BUY", "min_confidence": 0.56, "min_margin": 0.03},
            },
            "ranging": {
                "SELL": {"action": "SELL", "min_confidence": 0.60, "min_margin": 0.03},
                "BUY": {"action": "BUY", "min_confidence": 0.60, "min_margin": 0.03},
            },
        },
    }


def test_decision_governor_passes_directional_action() -> None:
    governor = DecisionGovernor()

    audit = governor.evaluate(
        preliminary_action="BUY",
        confidence=0.72,
        global_score=0.41,
        conflict_ratio=0.10,
        regime=MarketRegime.TRENDING.value,
        threshold_artifact=_artifact(),
    )

    assert audit.final_action == "BUY"
    assert audit.gate_decision is GateDecision.PASS
    assert audit.threshold_source == "global"
    assert audit.conflict_ratio == 0.10


def test_decision_governor_blocks_on_conflict_ratio() -> None:
    governor = DecisionGovernor()

    audit = governor.evaluate(
        preliminary_action="SELL",
        confidence=0.80,
        global_score=-0.50,
        conflict_ratio=0.90,
        regime=MarketRegime.RANGING.value,
        threshold_artifact=_artifact(),
    )

    assert audit.final_action == "HOLD"
    assert audit.gate_decision is GateDecision.BLOCK
    assert any("conflict_ratio" in reason for reason in audit.gate_reasons)


def test_decision_governor_weakens_on_higher_tf_penalty() -> None:
    governor = DecisionGovernor()

    audit = governor.evaluate(
        preliminary_action="BUY",
        confidence=0.90,
        global_score=0.35,
        conflict_ratio=0.10,
        regime=MarketRegime.TRENDING.value,
        threshold_artifact=_artifact(),
        higher_tf_aligned=False,
        higher_tf_detail="higher_tf_misaligned support=0 oppose=2",
    )

    assert audit.final_action == "BUY"
    assert audit.gate_decision is GateDecision.WEAKEN
    assert audit.final_confidence < audit.confidence_before
    assert any("higher_tf_penalty" in reason for reason in audit.gate_reasons)


def test_decision_governor_uses_ranging_fallback_when_global_missing() -> None:
    governor = DecisionGovernor()
    artifact = _artifact()
    artifact["thresholds"].pop("global")

    audit = governor.evaluate(
        preliminary_action="BUY",
        confidence=0.65,
        global_score=0.30,
        conflict_ratio=0.05,
        regime=MarketRegime.VOLATILE.value,
        threshold_artifact=artifact,
    )

    assert audit.final_action == "BUY"
    assert audit.threshold_source == "ranging"
