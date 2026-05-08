"""Regression tests for training runner safety checks."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.training.one_shot_dashboard import prepare_csv
from scripts.training.config import ASSETS
from scripts.training.runner import (
    _asset_output_dir,
    _build_exit_ai_command,
    _build_train_models_command,
)


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
    args = SimpleNamespace(min_data_months=6, exit_synthetic=360)
    output_dir = _asset_output_dir(ASSETS["silver"])

    train_command = _build_train_models_command(ASSETS["silver"], args, output_dir)
    exit_command = _build_exit_ai_command(args, output_dir)

    assert output_dir == "ai_engine/saved_models/assets/silver"
    assert train_command[train_command.index("--output") + 1] == output_dir
    assert exit_command[exit_command.index("--output") + 1] == output_dir
