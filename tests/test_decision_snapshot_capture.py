"""Tests for causal decision snapshot capture and distillation export."""

from __future__ import annotations

from ai_engine.training.decision_distill_dataset import materialize_distill_dataset
from ai_engine.training.decision_snapshot_capture import build_decision_snapshot


def _raw_signal(action: str = "BUY") -> dict:
    return {
        "action": action,
        "confidence": 0.72,
        "trade_score": 67,
        "entry_price": 2050.0,
        "stop_loss": 2048.0,
        "take_profit": 2055.0,
        "risk_reward_ratio": 2.5,
        "ensemble_probabilities": {"SELL": 0.10, "HOLD": 0.18, "BUY": 0.72},
        "final_aggregation": {
            "global_score": 0.42,
            "conflict_ratio": 0.12,
            "decision_audit": {
                "preliminary_action": action,
                "final_action": action,
            },
        },
    }


def test_decision_snapshot_preserves_action_hierarchy_for_blocked_trade() -> None:
    snapshot = build_decision_snapshot(
        raw_signal=_raw_signal("BUY"),
        final_signal={"action": "HOLD", "confidence": 0.0},
        block_stage="risk",
        block_codes=["MAX_DAILY_LOSS"],
    )

    payload = snapshot.to_dict()
    assert payload["preliminary_action"] == "BUY"
    assert payload["policy_action"] == "BUY"
    assert payload["final_action"] == "HOLD"
    assert payload["block_stage"] == "risk"
    assert payload["labels"]["blocked"] is True


def test_decision_snapshot_keeps_structured_failed_checks() -> None:
    snapshot = build_decision_snapshot(
        raw_signal=_raw_signal("SELL"),
        risk_approval={
            "approved": False,
            "failed_checks": [
                {"code": "SPREAD_TOO_WIDE", "value": 3.5, "limit": 2.0}
            ],
        },
    )

    assert snapshot.block_stage == "risk"
    assert snapshot.failed_checks[0]["code"] == "SPREAD_TOO_WIDE"
    assert snapshot.block_codes == ["SPREAD_TOO_WIDE"]


def test_future_outcome_mutation_does_not_change_policy_observation() -> None:
    first = build_decision_snapshot(
        raw_signal=_raw_signal("BUY"),
        realized_outcome={"pnl": 100.0},
    )
    second = build_decision_snapshot(
        raw_signal=_raw_signal("BUY"),
        realized_outcome={"pnl": -100.0},
    )

    assert first.observation == second.observation
    assert first.policy_action == second.policy_action


def test_materialize_distill_dataset_emits_manifest_and_block_summary() -> None:
    snapshots = [
        build_decision_snapshot(raw_signal=_raw_signal("BUY")),
        build_decision_snapshot(
            raw_signal=_raw_signal("SELL"),
            final_signal={"action": "HOLD"},
            block_stage="event",
            block_codes=["FOMC"],
        ),
    ]

    dataset = materialize_distill_dataset(snapshots)
    assert dataset["manifest"]["schema_version"] == 1
    assert "global_score" in dataset["manifest"]["feature_names"]
    assert dataset["label_summary"]["blocked_hold_count"] == 1


def test_blocked_decisions_are_not_flattened_to_generic_hold() -> None:
    snapshot = build_decision_snapshot(
        raw_signal=_raw_signal("BUY"),
        final_signal={"action": "HOLD"},
        block_stage="event_window",
        block_codes=["CPI"],
    )
    payload = snapshot.to_dict()

    assert payload["policy_action"] == "BUY"
    assert payload["final_action"] == "HOLD"
    assert payload["block_codes"] == ["CPI"]
