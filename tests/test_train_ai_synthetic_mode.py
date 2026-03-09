"""Tests for synthetic augmentation modes in scripts/train_ai.py."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from ai_engine.training.data_source import DataLoadResult
from scripts.train_ai import _apply_synthetic_mode


def _base_result(rows: int = 20) -> DataLoadResult:
    ts = pd.date_range("2026-02-23T00:00:00Z", periods=rows, freq="5min", tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": [2000.0 + i * 0.1 for i in range(rows)],
            "high": [2000.2 + i * 0.1 for i in range(rows)],
            "low": [1999.8 + i * 0.1 for i in range(rows)],
            "close": [2000.05 + i * 0.1 for i in range(rows)],
            "volume": [1000 + i for i in range(rows)],
        }
    )
    df.index = pd.to_datetime(df["timestamp"], utc=True)
    return DataLoadResult(
        source="file",
        timeframe="5m",
        dataframe=df,
        details={"source": "file", "rows": rows},
    )


def _args(mode: str) -> SimpleNamespace:
    return SimpleNamespace(
        synthetic_mode=mode,
        synthetic_rows=40,
        synthetic_seed=11,
        synthetic_switch_prob=0.03,
        synthetic_shock_prob=0.02,
        synthetic_gap_prob=0.01,
        synthetic_vol_scale=1.2,
    )


def test_apply_synthetic_mode_append() -> None:
    base = _base_result(20)
    out = _apply_synthetic_mode(base, _args("append"), with_indicators=False)
    assert out.source == "file+synthetic"
    assert len(out.dataframe) == 60
    assert out.details["synthetic_mode"] == "append"
    assert out.details["base_rows"] == 20
    assert out.details["synthetic_rows"] == 40


def test_apply_synthetic_mode_replace() -> None:
    base = _base_result(20)
    out = _apply_synthetic_mode(base, _args("replace"), with_indicators=False)
    assert out.source == "synthetic"
    assert len(out.dataframe) == 40
    assert out.details["synthetic_mode"] == "replace"
