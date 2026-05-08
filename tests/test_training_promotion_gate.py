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


def test_saved_training_report_shape_can_pass_gate() -> None:
    windows = [{"window_id": 0, "train_end": 1500, "test_start": 1560}]
    candidate = {
        "version": "candidate",
        "summary": {"n_windows": 1},
        "aggregate": {
            "best_model": "xgboost",
            "xgboost": {"profit_factor": 1.35, "n_trades": 60, "max_drawdown_pips": 90.0},
        },
        "split_manifest": {"windows": windows},
        "gate_metrics": {
            "profit_factor": 1.35,
            "max_drawdown": 90.0,
            "calibration_error": 0.04,
            "non_hold_trades": 60,
            "confidence_bucket_support": {"6": 30, "7": 35},
        },
        "confidence_buckets": {
            "6": {"support": 30, "actionable": True},
            "7": {"support": 35, "actionable": True},
        },
    }
    champion = {
        "version": "champion",
        "summary": {"n_windows": 1},
        "aggregate": {
            "best_model": "xgboost",
            "xgboost": {"profit_factor": 1.20, "n_trades": 60, "max_drawdown_pips": 85.0},
        },
        "split_manifest": {"windows": windows},
        "gate_metrics": {
            "profit_factor": 1.20,
            "max_drawdown": 85.0,
            "calibration_error": 0.05,
            "non_hold_trades": 60,
            "confidence_bucket_support": {"6": 30, "7": 35},
        },
        "confidence_buckets": {
            "6": {"support": 30, "actionable": True},
            "7": {"support": 35, "actionable": True},
        },
    }

    decision = evaluate_training_promotion(candidate, champion)

    assert decision["approved"] is True


def test_version_metadata_shape_can_supply_gate_windows_and_metrics() -> None:
    report = {
        "version": "candidate",
        "aggregate_metrics": {
            "xgboost": {"profit_factor": 1.35, "n_trades": 60, "max_drawdown_pips": 90.0},
        },
        "walk_forward": {
            "windows": [{"window_id": 0, "train_end": 1500, "test_start": 1560}],
        },
        "promotion_decision": {
            "gate_metrics": {
                "profit_factor": 1.35,
                "max_drawdown": 90.0,
                "calibration_error": 0.04,
                "non_hold_trades": 60,
                "confidence_bucket_support": 30,
            },
        },
    }

    decision = evaluate_training_promotion(report, {**report, "version": "champion"})

    assert "walk_forward_windows_missing" not in decision["reasons"]
    assert "candidate_missing_profit_factor" not in decision["reasons"]
