"""Tests for scripts.monitor_training_chart helpers."""

from __future__ import annotations

from scripts.monitor_training_chart import load_progress_records, render_line_chart


def test_load_progress_records_skips_invalid_lines(tmp_path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"cycle": 1, "profit_factor": 0.9}',
                "not-json",
                '{"cycle": 2, "profit_factor": 1.1}',
                "[]",
            ]
        ),
        encoding="utf-8",
    )

    rows = load_progress_records(path, max_records=100)
    assert len(rows) == 2
    assert rows[0]["cycle"] == 1
    assert rows[1]["cycle"] == 2


def test_render_line_chart_outputs_expected_shape() -> None:
    lines = render_line_chart([0.1, 0.3, 0.2, 0.7, 0.9], width=20, height=6)
    assert len(lines) == 7  # height + summary line
    assert lines[-1].startswith("min=")


def test_render_line_chart_no_data() -> None:
    lines = render_line_chart([], width=20, height=6)
    assert lines == ["(no data)"]

