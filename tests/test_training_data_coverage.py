"""Tests for training data coverage preflight and manifests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ai_engine.training.data_coverage import (
    DataCoverageError,
    build_dataset_manifest,
    build_row_loss_report,
    calculate_trainable_span,
    write_dataset_manifest,
)


def _ohlcv_frame(start: str, periods: int, freq: str = "5min") -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": ts,
            "open": 2040.0,
            "high": 2041.0,
            "low": 2039.0,
            "close": 2040.5,
            "volume": 1000,
        }
    )


def test_short_span_raises_with_diagnostic_keys() -> None:
    df = _ohlcv_frame("2026-04-13T00:00:00Z", periods=532)
    df.loc[len(df) - 1, "timestamp"] = pd.Timestamp("2026-04-14T20:15:00Z")

    with pytest.raises(DataCoverageError) as excinfo:
        calculate_trainable_span(df, min_months=1)

    message = str(excinfo.value)
    assert "trainable_days" in message
    assert "minimum_days" in message
    assert "start_timestamp" in message
    assert "end_timestamp" in message


def test_calculate_trainable_span_accepts_datetime_index() -> None:
    df = _ohlcv_frame("2026-01-01T00:00:00Z", periods=9000).set_index("timestamp")

    span = calculate_trainable_span(df, min_months=1)

    assert span["trainable_days"] >= 30.44
    assert span["rows"] == len(df)


def test_row_loss_report_tracks_stage_drops() -> None:
    report = build_row_loss_report(
        {
            "received": 1216,
            "saved": 520,
            "normalized": 520,
            "feature_ready": 480,
            "label_ready": 430,
        }
    )

    assert report["dropped_rows"]["received_to_saved"] == 696
    assert report["dropped_rows"]["normalized_to_feature_ready"] == 40
    assert report["dropped_rows"]["feature_ready_to_label_ready"] == 50


def test_dataset_manifest_contains_required_keys() -> None:
    df = _ohlcv_frame("2026-01-01T00:00:00Z", periods=100)
    row_loss = build_row_loss_report(
        {
            "received": 100,
            "saved": 95,
            "normalized": 95,
            "feature_ready": 90,
            "label_ready": 80,
        }
    )

    manifest = build_dataset_manifest(
        {"source": "file", "timeframe": "5m", "file_path": "data/gold_5m.csv"},
        df,
        row_loss,
        feature_set="core",
        label_set="entry",
        min_months=1,
    )

    for key in [
        "source",
        "timeframe",
        "received_rows",
        "saved_rows",
        "feature_ready_rows",
        "label_ready_rows",
        "trainable_days",
        "start_timestamp",
        "end_timestamp",
        "dropped_rows",
    ]:
        assert key in manifest
    assert manifest["label_ready_rows"] == 80


def test_write_dataset_manifest_round_trips_json(tmp_path) -> None:
    df = _ohlcv_frame("2026-01-01T00:00:00Z", periods=100)
    row_loss = build_row_loss_report(
        {
            "received": 100,
            "saved": 100,
            "normalized": 100,
            "feature_ready": 90,
            "label_ready": 80,
        }
    )
    manifest = build_dataset_manifest(
        {"source": "db", "timeframe": "5m"},
        df,
        row_loss,
        feature_set="core",
        label_set="entry",
        min_months=1,
    )

    path = write_dataset_manifest(manifest, tmp_path / "dataset_manifest.json")

    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    assert loaded["label_ready_rows"] == manifest["label_ready_rows"]
