"""Unit-Tests fuer Training-Datenquellenadapter."""

from __future__ import annotations

import pandas as pd
import pytest

from ai_engine.training.data_source import (
    DataSourceError,
    ensure_min_rows,
    load_from_file,
)


def test_load_from_file_normalizes_and_sorts(tmp_path) -> None:
    csv_path = tmp_path / "candles.csv"

    df = pd.DataFrame(
        {
            "timestamp": [
                "2026-02-23T10:10:00Z",
                "2026-02-23T10:00:00Z",
                "2026-02-23T10:05:00Z",
                "2026-02-23T10:05:00Z",
            ],
            "open": [2045.2, 2045.0, 2045.1, 2045.1],
            "high": [2045.4, 2045.3, 2045.2, 2045.2],
            "low": [2045.0, 2044.9, 2045.0, 2045.0],
            "close": [2045.3, 2045.1, 2045.2, 2045.2],
            "volume": [1200, 1000, 1100, 1100],
        }
    )
    df.to_csv(csv_path, index=False)

    loaded = load_from_file(str(csv_path), timeframe="5m", with_indicators=False)
    out = loaded.dataframe

    assert loaded.source == "file"
    assert len(out) == 3
    assert out["timestamp"].is_monotonic_increasing
    assert isinstance(out.index, pd.DatetimeIndex)
    assert set(["open", "high", "low", "close", "volume"]).issubset(out.columns)


def test_load_from_file_missing_required_column(tmp_path) -> None:
    csv_path = tmp_path / "invalid.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-02-23T10:00:00Z"],
            "open": [2045.0],
            "high": [2045.2],
            "low": [2044.9],
            # close fehlt
            "volume": [1000],
        }
    ).to_csv(csv_path, index=False)

    with pytest.raises(DataSourceError):
        load_from_file(str(csv_path), timeframe="5m", with_indicators=False)


def test_load_from_file_rejects_timeframe_mismatch(tmp_path) -> None:
    csv_path = tmp_path / "wrong_timeframe.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-02-23T10:00:00Z", "2026-02-23T10:05:00Z"],
            "open": [2045.0, 2045.1],
            "high": [2045.2, 2045.3],
            "low": [2044.8, 2044.9],
            "close": [2045.1, 2045.2],
            "volume": [1000, 1100],
            "timeframe": ["1m", "1m"],
        }
    ).to_csv(csv_path, index=False)

    with pytest.raises(DataSourceError, match="Timeframe '5m'"):
        load_from_file(str(csv_path), timeframe="5m", with_indicators=False)


def test_load_from_file_rejects_nan_ohlc_rows(tmp_path) -> None:
    csv_path = tmp_path / "nan_ohlc.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-02-23T10:00:00Z"],
            "open": [2045.0],
            "high": [2045.2],
            "low": [2044.8],
            "close": [None],
            "volume": [1000],
        }
    ).to_csv(csv_path, index=False)

    with pytest.raises(DataSourceError, match="NaN-Werten"):
        load_from_file(str(csv_path), timeframe="5m", with_indicators=False)


def test_load_from_file_rejects_invalid_ohlc_relationship(tmp_path) -> None:
    csv_path = tmp_path / "invalid_ohlc.csv"
    pd.DataFrame(
        {
            "timestamp": ["2026-02-23T10:00:00Z"],
            "open": [2045.0],
            "high": [2044.5],
            "low": [2044.8],
            "close": [2044.9],
            "volume": [1000],
        }
    ).to_csv(csv_path, index=False)

    with pytest.raises(DataSourceError, match="OHLC-Beziehung"):
        load_from_file(str(csv_path), timeframe="5m", with_indicators=False)


def test_ensure_min_rows() -> None:
    df = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=50, freq="5min", tz="UTC")})
    with pytest.raises(DataSourceError):
        ensure_min_rows(df, min_rows=100)
