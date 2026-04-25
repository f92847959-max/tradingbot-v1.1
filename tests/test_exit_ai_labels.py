"""Tests for causal Exit-AI snapshot generation."""

from __future__ import annotations

from ai_engine.training.exit_ai_labels import (
    EXIT_AI_ACTIONS,
    build_exit_training_samples,
)
from tests._exit_ai_fixtures import make_exit_ai_frame


def test_build_exit_training_samples_is_deterministic() -> None:
    frame = make_exit_ai_frame(rows=24)
    first = build_exit_training_samples(frame)
    second = build_exit_training_samples(frame)

    assert first["samples"] == second["samples"]
    assert first["feature_names"] == second["feature_names"]


def test_future_outcome_mutation_does_not_change_features_or_actions() -> None:
    frame = make_exit_ai_frame(rows=20)
    baseline = build_exit_training_samples(frame)

    mutated = frame.copy()
    mutated["future_adverse_r"] = mutated["future_adverse_r"] + 5.0
    mutated["future_favorable_r"] = mutated["future_favorable_r"] + 5.0
    changed = build_exit_training_samples(mutated)

    baseline_core = [
        {
            "features": sample["features"],
            "action": sample["action"],
            "action_label": sample["action_label"],
        }
        for sample in baseline["samples"]
    ]
    changed_core = [
        {
            "features": sample["features"],
            "action": sample["action"],
            "action_label": sample["action_label"],
        }
        for sample in changed["samples"]
    ]

    assert baseline_core == changed_core


def test_action_manifest_matches_allowed_action_set() -> None:
    dataset = build_exit_training_samples(make_exit_ai_frame(rows=16))
    assert tuple(dataset["action_manifest"]["allowed_actions"]) == EXIT_AI_ACTIONS
    assert set(dataset["class_balance"]["action_counts"]) == set(EXIT_AI_ACTIONS)


def test_unsafe_action_hint_is_rejected() -> None:
    frame = make_exit_ai_frame(rows=8)
    frame.loc[0, "action_hint"] = "BUY"

    try:
        build_exit_training_samples(frame)
    except ValueError as exc:
        assert "Unsafe Exit-AI action" in str(exc)
    else:
        raise AssertionError("Expected unsafe action hint to be rejected")
