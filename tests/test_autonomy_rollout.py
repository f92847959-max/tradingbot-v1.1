"""Tests for autonomy-head rollout selection and governance metadata."""

from __future__ import annotations

from ai_engine.prediction.decision_head import DecisionHeadPrediction, apply_autonomy_rollout
from trading.trading_loop import build_rollout_evaluation_summary


def test_shadow_mode_executes_champion_and_logs_candidate() -> None:
    selected, metadata = apply_autonomy_rollout(
        {"action": "BUY", "confidence": 0.7},
        DecisionHeadPrediction(
            action="SELL",
            confidence=0.9,
            probabilities={"SELL": 0.9, "HOLD": 0.05, "BUY": 0.05},
        ),
        mode="shadow",
    )

    assert selected["action"] == "BUY"
    assert metadata["selected_source"] == "champion"
    assert metadata["disagreement"] is True


def test_agreement_guarded_falls_back_to_champion_on_disagreement() -> None:
    selected, metadata = apply_autonomy_rollout(
        {"action": "BUY", "confidence": 0.7},
        DecisionHeadPrediction(
            action="SELL",
            confidence=0.9,
            probabilities={"SELL": 0.9, "HOLD": 0.05, "BUY": 0.05},
        ),
        mode="agreement_guarded",
    )

    assert selected["action"] == "BUY"
    assert metadata["selected_source"] == "champion"


def test_primary_with_challenger_selects_candidate_without_guard_bypass() -> None:
    selected, metadata = apply_autonomy_rollout(
        {"action": "BUY", "confidence": 0.7},
        DecisionHeadPrediction(
            action="SELL",
            confidence=0.9,
            probabilities={"SELL": 0.9, "HOLD": 0.05, "BUY": 0.05},
        ),
        mode="primary_with_challenger",
    )

    assert selected["action"] == "SELL"
    assert metadata["selected_source"] == "candidate"
    assert metadata["guard_bypass_count"] == 0


def test_missing_candidate_artifacts_degrade_to_champion_behavior() -> None:
    selected, metadata = apply_autonomy_rollout(
        {"action": "BUY", "confidence": 0.7},
        {"action": "HOLD", "confidence": 0.0, "available": False},
        mode="primary_with_challenger",
    )

    assert selected["action"] == "BUY"
    assert metadata["selected_source"] == "champion"


def test_rollout_evaluation_summary_preserves_pre_ai_blocks() -> None:
    summary = build_rollout_evaluation_summary(
        None,
        rejection_reason="event_window",
        pre_ai_block={
            "block_stage": "event_window",
            "block_codes": ["FOMC"],
        },
    )

    assert summary["pre_ai_block"]["block_codes"] == ["FOMC"]
    assert summary["guard_bypass_count"] == 0
