"""Tests for hybrid source loading behavior in scripts/train_ai.py."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pandas as pd
import pytest

from ai_engine.training.data_source import DataLoadResult, DataSourceError
from scripts.train_ai import load_training_data


def _base_df(rows: int = 20) -> pd.DataFrame:
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
    return df


def _args() -> SimpleNamespace:
    return SimpleNamespace(
        source="hybrid",
        no_indicators=True,
        count=100,
        timeframe="5m",
        file_path=None,
        synthetic_mode="off",
        synthetic_rows=12,
        synthetic_seed=7,
        synthetic_switch_prob=0.03,
        synthetic_shock_prob=0.02,
        synthetic_gap_prob=0.01,
        synthetic_vol_scale=1.2,
        hybrid_real_source_order="broker_live,auto",
        hybrid_require_real=False,
    )


def test_hybrid_uses_real_source_and_appends_synthetic(monkeypatch) -> None:
    async def fake_broker(*_args, **_kwargs) -> DataLoadResult:
        df = _base_df(20)
        return DataLoadResult(
            source="broker_live",
            timeframe="5m",
            dataframe=df,
            details={"source": "broker_live", "timeframe": "5m", "rows": len(df)},
        )

    async def fake_auto(*_args, **_kwargs) -> DataLoadResult:
        raise AssertionError("auto fallback should not be used when broker succeeds")

    monkeypatch.setattr("scripts.train_ai._load_from_broker_live", fake_broker)
    monkeypatch.setattr("scripts.train_ai.load_auto", fake_auto)

    result = asyncio.run(load_training_data(_args()))

    assert result.source == "broker_live+synthetic"
    assert len(result.dataframe) == 32
    assert result.details["hybrid"]["selected_source"] == "broker_live"
    assert result.details["hybrid"]["synthetic_mode_used"] == "append"
    assert not result.details["hybrid"]["fallback_to_synthetic_only"]


def test_hybrid_falls_back_to_synthetic_when_real_sources_fail(monkeypatch) -> None:
    async def fail_broker(*_args, **_kwargs) -> DataLoadResult:
        raise DataSourceError("broker unavailable")

    async def fail_auto(*_args, **_kwargs) -> DataLoadResult:
        raise DataSourceError("auto unavailable")

    monkeypatch.setattr("scripts.train_ai._load_from_broker_live", fail_broker)
    monkeypatch.setattr("scripts.train_ai.load_auto", fail_auto)

    result = asyncio.run(load_training_data(_args()))

    assert result.source == "synthetic"
    assert result.details["hybrid"]["selected_source"] == "synthetic_fallback"
    assert result.details["hybrid"]["fallback_to_synthetic_only"]
    assert len(result.details["hybrid"]["attempts"]) == 2


def test_hybrid_require_real_raises_if_all_real_sources_fail(monkeypatch) -> None:
    async def fail_broker(*_args, **_kwargs) -> DataLoadResult:
        raise DataSourceError("broker unavailable")

    async def fail_auto(*_args, **_kwargs) -> DataLoadResult:
        raise DataSourceError("auto unavailable")

    args = _args()
    args.hybrid_require_real = True

    monkeypatch.setattr("scripts.train_ai._load_from_broker_live", fail_broker)
    monkeypatch.setattr("scripts.train_ai.load_auto", fail_auto)

    with pytest.raises(DataSourceError):
        asyncio.run(load_training_data(args))

