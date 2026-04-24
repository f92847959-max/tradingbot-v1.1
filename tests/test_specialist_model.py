"""Tests for isolated specialist training artifacts."""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd
import pytest

from ai_engine.training.model_versioning import (
    create_specialist_version_dir,
    get_specialist_root,
    update_specialist_production_pointer,
)
from ai_engine.training.specialist_pipeline import (
    DEFAULT_SPECIALIST_NAME,
    load_specialist_bundle,
    train_specialist_model,
)


def _training_df(rows: int = 480) -> pd.DataFrame:
    ts = pd.date_range("2026-04-01T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    rng = np.random.default_rng(321)
    wave = np.sin(np.linspace(0.0, 14.0 * np.pi, rows)) * 0.9
    drift = np.linspace(-1.5, 1.8, rows)
    close = 2050.0 + drift + wave + rng.normal(0.0, 0.12, rows)

    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": close + rng.normal(0.0, 0.05, rows),
            "high": close + np.abs(rng.normal(0.22, 0.07, rows)),
            "low": close - np.abs(rng.normal(0.22, 0.07, rows)),
            "close": close,
            "volume": rng.integers(700, 2400, rows),
            "atr_14": np.clip(rng.normal(1.15, 0.14, rows), 0.35, None),
            "rsi_14": rng.uniform(20.0, 80.0, rows),
            "macd_line": rng.normal(0.0, 0.25, rows),
            "macd_signal": rng.normal(0.0, 0.20, rows),
            "macd_hist": rng.normal(0.0, 0.08, rows),
            "ema_9": close + rng.normal(0.0, 0.05, rows),
            "ema_21": close + rng.normal(0.0, 0.05, rows),
            "ema_50": close + rng.normal(0.0, 0.05, rows),
            "ema_200": np.full(rows, 2048.5),
            "bb_width": rng.uniform(0.006, 0.018, rows),
            "bb_position": rng.uniform(0.0, 1.0, rows),
            "adx_14": rng.uniform(12.0, 38.0, rows),
            "stoch_k": rng.uniform(10.0, 90.0, rows),
            "stoch_d": rng.uniform(10.0, 90.0, rows),
            "pivot": np.full(rows, 2050.0),
            "pivot_s1": np.full(rows, 2046.0),
            "pivot_r1": np.full(rows, 2054.0),
            "vwap": np.full(rows, 2050.4),
        },
        index=ts,
    )

    forward = pd.Series(close, index=ts).shift(-6).ffill()
    delta = forward - close
    df["label"] = np.where(delta > 0.18, 1, np.where(delta < -0.18, -1, 0))
    return df


def test_train_specialist_model_saves_isolated_artifacts(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    result = train_specialist_model(
        _training_df(),
        saved_models_dir=str(saved_models_dir),
    )

    specialist_root = get_specialist_root(
        str(saved_models_dir),
        DEFAULT_SPECIALIST_NAME,
    )
    assert result["specialist_root"] == specialist_root
    assert os.path.isdir(result["version_dir"])
    assert result["version_dir"].startswith(specialist_root)

    for filename in (
        "specialist_lightgbm.pkl",
        "specialist_scaler.pkl",
        "specialist_version.json",
        "feature_block.json",
        "production.json",
    ):
        target = (
            os.path.join(specialist_root, filename)
            if filename == "production.json"
            else os.path.join(result["version_dir"], filename)
        )
        assert os.path.exists(target), target

    assert not os.path.exists(saved_models_dir / "lightgbm_gold.pkl")
    assert not os.path.exists(saved_models_dir / "production.json")


def test_specialist_production_pointer_does_not_touch_core_files(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    saved_models_dir.mkdir(parents=True)

    core_model = saved_models_dir / "lightgbm_gold.pkl"
    core_model.write_bytes(b"core-model")
    before = core_model.stat().st_mtime_ns
    time.sleep(0.01)

    version_dir = create_specialist_version_dir(
        str(saved_models_dir),
        DEFAULT_SPECIALIST_NAME,
    )
    for filename in (
        "specialist_lightgbm.pkl",
        "specialist_scaler.pkl",
        "specialist_version.json",
        "feature_block.json",
    ):
        with open(os.path.join(version_dir, filename), "wb") as f:
            f.write(b"specialist")
    with open(os.path.join(version_dir, "version.json"), "w", encoding="utf-8") as f:
        json.dump({"version": "v001"}, f)

    pointer_path = update_specialist_production_pointer(
        str(saved_models_dir),
        DEFAULT_SPECIALIST_NAME,
        version_dir,
    )

    assert os.path.exists(pointer_path)
    assert core_model.stat().st_mtime_ns == before
    assert not os.path.exists(saved_models_dir / "specialist_lightgbm.pkl")


def test_load_specialist_bundle_rejects_feature_block_mismatch(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    train_specialist_model(
        _training_df(),
        saved_models_dir=str(saved_models_dir),
    )

    with pytest.raises(ValueError, match="Feature block mismatch"):
        load_specialist_bundle(
            str(saved_models_dir),
            expected_features=["wrong_feature"],
        )
