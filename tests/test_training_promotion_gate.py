"""Tests for Phase 12.7 training promotion gates."""

from __future__ import annotations

import json

from ai_engine.training.promotion_gate import (
    build_shadow_training_manifest,
    evaluate_training_promotion,
    write_promotion_decision,
)


def _report(
    *,
    version: str,
    pf: float,
    drawdown: float,
    calibration: float,
    bucket_support: int,
    non_hold: int,
) -> dict:
    return {
        "version": version,
        "profit_factor": pf,
        "max_drawdown": drawdown,
        "calibration_error": calibration,
        "non_hold_trades": non_hold,
        "confidence_buckets": {
            "0.60_0.70": {"support": bucket_support, "actionable": True},
            "0.70_1.00": {"support": bucket_support + 5, "actionable": True},
        },
        "split_manifest": {
            "windows": [{"window_id": 0, "train_end": 1500, "test_start": 1560}]
        },
    }


def test_candidate_passes_when_all_gates_pass() -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.30,
            drawdown=0.105,
            calibration=0.05,
            bucket_support=25,
            non_hold=40,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    assert decision["approved"] is True
    assert decision["mode"] == "shadow_ready"


def test_candidate_blocks_on_calibration_error() -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.40,
            drawdown=0.10,
            calibration=0.12,
            bucket_support=25,
            non_hold=40,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    assert decision["approved"] is False
    assert "calibration_error_above_limit" in decision["reasons"]


def test_candidate_blocks_on_drawdown_worsening() -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.40,
            drawdown=0.12,
            calibration=0.05,
            bucket_support=25,
            non_hold=40,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    assert decision["approved"] is False
    assert "drawdown_worse_than_allowed" in decision["reasons"]


def test_candidate_blocks_on_non_hold_trade_count() -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.40,
            drawdown=0.10,
            calibration=0.05,
            bucket_support=25,
            non_hold=5,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    assert decision["approved"] is False
    assert "non_hold_trade_count_below_minimum" in decision["reasons"]


def test_write_promotion_decision_round_trips(tmp_path) -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.40,
            drawdown=0.10,
            calibration=0.05,
            bucket_support=25,
            non_hold=40,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    path = write_promotion_decision(decision, tmp_path / "promotion_decision.json")
    loaded = json.loads((tmp_path / "promotion_decision.json").read_text())

    assert path.endswith("promotion_decision.json")
    for key in [
        "approved",
        "reasons",
        "gate_metrics",
        "candidate_version",
        "champion_version",
    ]:
        assert key in loaded


def test_failed_promotion_is_data_only_and_requires_no_pointer_update() -> None:
    decision = evaluate_training_promotion(
        _report(
            version="candidate",
            pf=1.40,
            drawdown=0.10,
            calibration=0.12,
            bucket_support=25,
            non_hold=40,
        ),
        _report(
            version="champion",
            pf=1.20,
            drawdown=0.10,
            calibration=0.06,
            bucket_support=25,
            non_hold=40,
        ),
    )

    manifest = build_shadow_training_manifest(
        decision,
        {"source": "file", "label_ready_rows": 5000},
        {"window_count": 1},
    )

    assert decision["approved"] is False
    assert "update_production_pointer" not in decision
    assert manifest["approved"] is False
