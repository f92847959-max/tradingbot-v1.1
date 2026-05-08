"""Regression tests for training runner safety checks."""

from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.training.config import ASSETS, PROJECT_ROOT
from scripts.training.one_shot_dashboard import prepare_csv
from scripts.training.runner import (
    _asset_output_dir,
    _build_exit_ai_command,
    _build_train_models_command,
)
from start_ai_training import ExitJobSkipped, _build_exit_job


def test_prepare_csv_rejects_source_overwrite(tmp_path) -> None:
    csv_path = tmp_path / "gold_1h.csv"
    pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-01-01", periods=3, freq="1h", tz="UTC",
            ),
            "open": [1.0, 2.0, 3.0],
            "high": [1.5, 2.5, 3.5],
            "low": [0.5, 1.5, 2.5],
            "close": [1.2, 2.2, 3.2],
            "volume": [10, 20, 30],
        }
    ).to_csv(csv_path, index=False)

    with pytest.raises(ValueError, match="must not overwrite"):
        prepare_csv(csv_path, csv_path, "1h")


def test_silver_training_uses_asset_scoped_model_output() -> None:
    args = SimpleNamespace(
        min_data_months=6,
        exit_csv="data/exit_ai_snapshots.csv",
        exit_synthetic=0,
    )
    output_dir = _asset_output_dir(ASSETS["silver"])

    train_command = _build_train_models_command(ASSETS["silver"], args, output_dir)
    exit_command = _build_exit_ai_command(args, output_dir)

    assert output_dir == "ai_engine/saved_models/assets/silver"
    assert train_command[train_command.index("--output") + 1] == output_dir
    assert exit_command[exit_command.index("--output") + 1] == output_dir


def test_continuous_loop_uses_real_exit_csv_by_default() -> None:
    args = SimpleNamespace(exit_csv="data/exit_ai_snapshots.csv", exit_synthetic=0)

    command = _build_exit_ai_command(args, "ai_engine/saved_models")

    assert "--csv" in command
    assert command[command.index("--csv") + 1] == "data/exit_ai_snapshots.csv"
    assert "--synthetic" not in command


def test_continuous_loop_synthetic_exit_requires_explicit_flag() -> None:
    args = SimpleNamespace(exit_csv="data/exit_ai_snapshots.csv", exit_synthetic=360)

    command = _build_exit_ai_command(args, "ai_engine/saved_models")

    assert "--synthetic" in command
    assert command[command.index("--synthetic") + 1] == "360"
    assert "--csv" not in command


def test_start_ai_training_missing_exit_csv_is_fatal_by_default(tmp_path) -> None:
    args = SimpleNamespace(
        exit_csv=str(tmp_path / "missing_exit.csv"),
        exit_min_samples=500,
        exit_purge_gap=12,
        exit_min_train_samples=120,
        exit_min_test_samples=40,
        output="ai_engine/saved_models",
    )

    with pytest.raises(FileNotFoundError, match="Exit-AI real snapshot CSV missing"):
        _build_exit_job(args, validate_csv=True, soft_skip=False)

    with pytest.raises(ExitJobSkipped):
        _build_exit_job(args, validate_csv=True, soft_skip=True)


def test_train_models_csv_dry_run_validates_missing_csv(tmp_path) -> None:
    missing = tmp_path / "missing.csv"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/train_models.py",
            "--csv",
            str(missing),
            "--dry-run",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode != 0
    assert "missing.csv" in (result.stderr + result.stdout)
