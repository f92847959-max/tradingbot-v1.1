"""Tests for progress JSONL helpers in scripts/train_ai.py."""

from __future__ import annotations

import json

from scripts.train_ai import append_progress_jsonl, build_cycle_progress_entry


def test_build_cycle_progress_entry_has_expected_fields() -> None:
    row = build_cycle_progress_entry(
        cycle=3,
        data_details={"source": "hybrid", "rows": 4200},
        best_metrics={
            "best_model": "XGBoost",
            "best_trading": {
                "profit_factor": 1.45,
                "sharpe_ratio": 1.11,
                "win_rate": 0.57,
                "n_trades": 75,
            },
            "best_ml": {"accuracy": 0.83, "f1_score": 0.79},
            "backtest": {"max_drawdown_pct": 9.2},
        },
        acceptance={"overall": "borderline"},
        elapsed_seconds=123.4567,
    )

    assert row["cycle"] == 3
    assert row["source_used"] == "hybrid"
    assert row["rows"] == 4200
    assert row["acceptance"] == "borderline"
    assert row["best_model"] == "XGBoost"
    assert row["profit_factor"] == 1.45
    assert row["sharpe_ratio"] == 1.11
    assert row["win_rate"] == 0.57
    assert row["n_trades"] == 75
    assert row["max_drawdown_pct"] == 9.2
    assert row["ml_accuracy"] == 0.83
    assert row["ml_f1"] == 0.79
    assert row["elapsed_seconds"] == 123.457


def test_append_progress_jsonl_appends_rows(tmp_path) -> None:
    out = tmp_path / "training_progress.jsonl"

    append_progress_jsonl(str(out), {"cycle": 1, "profit_factor": 0.9})
    append_progress_jsonl(str(out), {"cycle": 2, "profit_factor": 1.2})

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 2
    assert rows[0]["cycle"] == 1
    assert rows[1]["cycle"] == 2


def test_append_progress_jsonl_with_none_path_is_noop() -> None:
    append_progress_jsonl(None, {"cycle": 1})

