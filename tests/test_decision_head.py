"""Tests for decision-head training, artifacts, and rollout contract."""

from __future__ import annotations

import os

from ai_engine.calibration.artifacts import (
    load_calibration_artifact,
    load_threshold_artifact,
)
from ai_engine.prediction.decision_head import (
    DecisionHeadPrediction,
    DecisionHeadRuntime,
    apply_autonomy_rollout,
)
from ai_engine.training.decision_distill_dataset import materialize_distill_dataset
from ai_engine.training.decision_head_pipeline import (
    compare_decision_head_to_champion,
    evaluate_decision_head_candidate,
    train_decision_head,
)
from ai_engine.training.decision_snapshot_capture import build_decision_snapshot


def _signal(action: str, confidence: float, score: float) -> dict:
    return {
        "action": action,
        "confidence": confidence,
        "trade_score": int(confidence * 100),
        "entry_price": 2050.0,
        "stop_loss": 2048.0,
        "take_profit": 2055.0,
        "risk_reward_ratio": 2.5,
        "ensemble_probabilities": {
            "SELL": 0.75 if action == "SELL" else 0.10,
            "HOLD": 0.75 if action == "HOLD" else 0.10,
            "BUY": 0.75 if action == "BUY" else 0.10,
        },
        "final_aggregation": {
            "global_score": score,
            "conflict_ratio": 0.05,
            "decision_audit": {"preliminary_action": action},
        },
    }


def _dataset(rows: int = 220):
    snapshots = []
    actions = ["SELL", "HOLD", "BUY"]
    for idx in range(rows):
        action = actions[idx % 3]
        score = -0.6 if action == "SELL" else (0.6 if action == "BUY" else 0.0)
        snapshots.append(
            build_decision_snapshot(
                raw_signal=_signal(action, 0.68 + ((idx % 5) * 0.03), score),
                policy_signal={"action": action, "confidence": 0.7},
                block_stage="none",
            )
        )
    return materialize_distill_dataset(snapshots)


def test_train_decision_head_saves_isolated_artifacts_and_calibration(tmp_path) -> None:
    dataset = _dataset()
    result = train_decision_head(
        dataset["frame"],
        feature_names=dataset["manifest"]["feature_names"],
        saved_models_dir=str(tmp_path / "saved_models"),
    )

    assert os.path.exists(os.path.join(result["version_dir"], "decision_head_model.pkl"))
    assert os.path.exists(os.path.join(result["version_dir"], "decision_head_scaler.pkl"))
    assert load_calibration_artifact(result["version_dir"])["class_labels"] == [
        "SELL",
        "HOLD",
        "BUY",
    ]
    assert load_threshold_artifact(result["version_dir"])["schema_version"] == 1


def test_decision_head_runtime_outputs_buy_hold_sell_only(tmp_path) -> None:
    dataset = _dataset()
    train_decision_head(
        dataset["frame"],
        feature_names=dataset["manifest"]["feature_names"],
        saved_models_dir=str(tmp_path / "saved_models"),
    )

    runtime = DecisionHeadRuntime(saved_models_dir=str(tmp_path / "saved_models"))
    prediction = runtime.predict_from_signal(_signal("BUY", 0.8, 0.6))
    assert prediction.action in {"SELL", "HOLD", "BUY"}
    assert prediction.available is True


def test_compare_decision_head_to_champion_reports_disagreement_buckets() -> None:
    dataset = _dataset(rows=260)
    report = compare_decision_head_to_champion(
        dataset["frame"],
        feature_names=dataset["manifest"]["feature_names"],
        min_train_samples=120,
        min_test_samples=40,
    )

    assert report["schema_version"] == 1
    assert report["window_count"] >= 1
    assert "disagreement_buckets" in report
    assert "profit_factor_delta" in report["deltas"]


def test_evaluate_decision_head_candidate_rejects_hold_dominant_behavior() -> None:
    evaluation = evaluate_decision_head_candidate(
        {"profit_factor": 1.2, "calibration_score": 0.7},
        {"profit_factor": 1.4, "calibration_score": 0.7, "hold_rate": 0.95},
    )
    assert evaluation["promote"] is False
    assert any("HOLD" in reason for reason in evaluation["reasons"])


def test_apply_autonomy_rollout_preserves_shadow_champion() -> None:
    champion = {"action": "BUY", "confidence": 0.70}
    selected, metadata = apply_autonomy_rollout(
        champion,
        DecisionHeadPrediction(
            action="SELL",
            confidence=0.80,
            probabilities={"SELL": 0.8, "HOLD": 0.1, "BUY": 0.1},
        ),
        mode="shadow",
    )

    assert selected["action"] == "BUY"
    assert metadata["disagreement"] is True
    assert metadata["guard_bypass_count"] == 0
