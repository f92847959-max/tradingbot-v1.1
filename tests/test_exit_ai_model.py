"""Tests for isolated Exit-AI artifact storage and loading."""

from __future__ import annotations

import os

import pytest

from ai_engine.training.exit_ai_pipeline import (
    DEFAULT_EXIT_AI_NAME,
    load_exit_ai_bundle,
    train_exit_ai_specialist,
)
from ai_engine.training.model_versioning import get_specialist_root
from tests._exit_ai_fixtures import make_exit_ai_frame


def test_train_exit_ai_specialist_saves_isolated_artifacts(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    result = train_exit_ai_specialist(
        make_exit_ai_frame(),
        saved_models_dir=str(saved_models_dir),
    )

    specialist_root = get_specialist_root(str(saved_models_dir), DEFAULT_EXIT_AI_NAME)
    assert result["specialist_root"] == specialist_root
    assert result["version_dir"].startswith(specialist_root)

    for filename in (
        "exit_ai_lightgbm.pkl",
        "exit_ai_scaler.pkl",
        "feature_block.json",
        "action_manifest.json",
        "exit_ai_version.json",
        "exit_ai_training_report.json",
    ):
        assert os.path.exists(os.path.join(result["version_dir"], filename))

    assert os.path.exists(os.path.join(specialist_root, "production.json"))
    assert not os.path.exists(saved_models_dir / "lightgbm_gold.pkl")


def test_load_exit_ai_bundle_rejects_feature_block_mismatch(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    train_exit_ai_specialist(
        make_exit_ai_frame(),
        saved_models_dir=str(saved_models_dir),
    )

    with pytest.raises(ValueError, match="Feature block mismatch"):
        load_exit_ai_bundle(
            str(saved_models_dir),
            expected_features=["wrong_feature"],
        )
