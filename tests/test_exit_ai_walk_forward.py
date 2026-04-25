"""Tests for leak-free Exit-AI walk-forward comparison."""

from __future__ import annotations

from ai_engine.training.exit_ai_pipeline import compare_exit_ai_to_baseline
from tests._exit_ai_fixtures import make_exit_ai_frame


def test_compare_exit_ai_to_baseline_reports_stable_schema() -> None:
    report = compare_exit_ai_to_baseline(
        make_exit_ai_frame(rows=320),
        min_train_samples=120,
        min_test_samples=40,
    )

    assert report["schema_version"] == 1
    assert report["window_count"] >= 1
    assert "baseline" in report["comparison"]
    assert "exit_ai_candidate" in report["comparison"]
    assert "drawdown_contained" in report["comparison"]["baseline"]
    assert "upside_retained" in report["comparison"]["exit_ai_candidate"]


def test_compare_exit_ai_to_baseline_preserves_purge_gap_and_train_only_scaling() -> None:
    report = compare_exit_ai_to_baseline(
        make_exit_ai_frame(rows=320),
        purge_gap=14,
        min_train_samples=120,
        min_test_samples=40,
    )

    assert report["purge_gap"] == 14
    assert all(window["purge_gap"] == 14 for window in report["windows"])
    assert all(window["scaler_scope"] == "train_only" for window in report["windows"])
