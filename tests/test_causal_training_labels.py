"""Tests for causal training label helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.training.causal_training_labels import (
    CausalLabelConfig,
    build_causal_label_frame,
    build_label_manifest,
    build_split_manifest,
)
from ai_engine.training.label_generator import LabelGenerator
from ai_engine.training.walk_forward import WindowSpec


def _frame(rows: int = 120) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC")
    close = 2040.0 + np.sin(np.linspace(0.0, 8.0, rows))
    return pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1000,
            "atr_14": np.linspace(0.2, 1.2, rows),
        },
        index=idx,
    )


def test_causal_label_frame_schema() -> None:
    labels = build_causal_label_frame(_frame(), LabelGenerator(max_candles=10))

    assert {
        "entry_label",
        "abstain_label",
        "exit_label",
        "confidence_target",
        "risk_bucket",
    }.issubset(labels.columns)


def test_entry_label_matches_existing_generator() -> None:
    df = _frame()
    generator = LabelGenerator(max_candles=10)

    labels = build_causal_label_frame(df, generator)

    expected = generator.generate_labels(df)
    pd.testing.assert_series_equal(
        labels["entry_label"],
        expected.rename("entry_label").astype(int),
    )


def test_future_row_mutation_does_not_change_current_input_metadata() -> None:
    df = _frame()
    generator = LabelGenerator(max_candles=10)
    baseline = build_causal_label_frame(df, generator)

    mutated = df.copy()
    mutated.iloc[50:, mutated.columns.get_loc("high")] += 500.0
    mutated_labels = build_causal_label_frame(mutated, generator)

    assert baseline.loc[df.index[10], "risk_bucket"] == mutated_labels.loc[
        df.index[10],
        "risk_bucket",
    ]
    assert "entry_label" not in ["atr_14", "open", "high", "low", "close"]


def test_label_manifest_contains_required_keys() -> None:
    config = CausalLabelConfig(max_holding_candles=12, spread_pips=2.5)

    manifest = build_label_manifest(
        config,
        ["entry_label", "abstain_label", "confidence_target", "risk_bucket"],
    )

    for key in [
        "schema_version",
        "label_columns",
        "entry_label_source",
        "max_holding_candles",
        "spread_pips",
        "generated_at",
    ]:
        assert key in manifest


def test_split_manifest_contains_windows_and_schema() -> None:
    windows = [WindowSpec(0, 0, 100, 110, 150)]

    manifest = build_split_manifest(
        windows,
        purge_gap=10,
        feature_names=["rsi_14", "entry_label", "atr_14"],
        label_columns=["entry_label", "confidence_target"],
    )

    assert manifest["purge_gap"] == 10
    assert manifest["window_count"] == 1
    assert "entry_label" not in manifest["feature_names"]
    assert manifest["label_columns"] == ["entry_label", "confidence_target"]
    assert manifest["windows"][0]["purge_gap"] == 10
