from __future__ import annotations

import random

from ui_demo_app.analysis import SUMMARY_MARKER, build_analysis_prompt, extract_summary
from ui_demo_app.config import DemoConfig
from ui_demo_app.layout import progress_bar
from ui_demo_app.simulator import TrainingSimulator, TrainingStats


def test_extract_summary_prefers_marker_tail() -> None:
    text = f"Langbericht\n{SUMMARY_MARKER}\nKurzfassung"

    assert extract_summary(text) == "Kurzfassung"


def test_analysis_prompt_contains_gate_marker() -> None:
    stats = TrainingStats(
        epochs=5,
        final_eq=1010.0,
        best_eq=1020.0,
        final_acc=0.56,
        best_acc=0.6,
        final_loss=0.8,
        min_loss=0.7,
        duration_sec=1.5,
    )

    prompt = build_analysis_prompt(stats)

    assert SUMMARY_MARKER in prompt
    assert "Win Rate: 56.0%" in prompt


def test_config_from_env_keeps_gemini_key_optional(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("UI_DEMO_MAX_EPOCHS", "7")
    monkeypatch.setenv("UI_DEMO_REPORT_PATH", str(tmp_path / "report.txt"))

    config = DemoConfig.from_env()

    assert config.max_epochs == 7
    assert config.gemini_api_key is None
    assert config.report_path == tmp_path / "report.txt"


def test_training_simulator_trims_series_history() -> None:
    config = DemoConfig(max_epochs=4, history_len=2)
    simulator = TrainingSimulator(config, rng=random.Random(1))

    frame = None
    for epoch in range(1, 5):
        frame = simulator.step(epoch)

    assert frame is not None
    assert len(frame.series.equity) == 2
    assert len(frame.series.validation_loss) == 2
    assert frame.stats.epochs == 4


def test_progress_bar_is_width_stable() -> None:
    assert progress_bar(2, 4, width=4) == "##--"
