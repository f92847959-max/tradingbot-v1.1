"""Tests for the Phase 18 --max-history cache-and-extend behaviour.

The Dukascopy broker call is never exercised; the helpers are designed so the
cache-fully-covered path returns without importing or invoking the broker.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from scripts.fetch_bulk_history import (
    MAX_HISTORY_YEARS,
    compute_cached_range,
    fetch_with_cache,
)


def _write_cache(path: Path, *, first: datetime, last: datetime, periods: int = 10) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = pd.date_range(first, last, periods=periods, tz="UTC")
    df = pd.DataFrame(
        {
            "timestamp": ts,
            "open": 2000.0,
            "high": 2001.0,
            "low": 1999.0,
            "close": 2000.5,
            "volume": 100.0,
        }
    )
    df.to_csv(path, index=False)


def test_compute_cached_range_missing_returns_none(tmp_path: Path) -> None:
    assert compute_cached_range(tmp_path / "missing.csv") is None


def test_compute_cached_range_reads_csv(tmp_path: Path) -> None:
    csv = tmp_path / "gold_5m.csv"
    first = datetime(2020, 1, 1, tzinfo=timezone.utc)
    last = datetime(2026, 5, 1, tzinfo=timezone.utc)
    _write_cache(csv, first=first, last=last)

    span = compute_cached_range(csv)

    assert span is not None
    span_first, span_last = span
    assert span_first <= first + pd.Timedelta(seconds=1)
    assert span_last >= last - pd.Timedelta(seconds=1)


def test_fetch_with_cache_no_op_when_cache_covers_requested_range(tmp_path: Path) -> None:
    """When the existing CSV already covers max-history, no broker call happens.

    This is the core guarantee of cache-and-extend semantics: --max-history on a
    fully-populated dataset must NOT re-hit Dukascopy.
    """
    csv = tmp_path / "gold_5m.csv"
    # Cache covers from MAX_HISTORY_YEARS + 1 ago through tomorrow — fully
    # covers any window the helper might request.
    end = datetime.now(tz=timezone.utc) + pd.Timedelta(days=1)
    first = pd.Timestamp(end) - pd.DateOffset(years=MAX_HISTORY_YEARS + 1)
    _write_cache(csv, first=first.to_pydatetime(), last=end)

    # Patch BOTH the broker importer and the fetch helper so we can assert
    # neither was touched.
    with (
        patch("scripts.fetch_bulk_history._import_dukascopy") as mock_import,
        patch("scripts.fetch_bulk_history._fetch_timeframe_directly") as mock_fetch,
    ):
        result = fetch_with_cache(
            "XAU/USD",
            "5m",
            max_history=True,
            years_cap=None,
            output_dir=tmp_path,
        )

    assert result == csv
    mock_import.assert_not_called()
    mock_fetch.assert_not_called()


def test_fetch_with_cache_requires_max_history_or_years_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_history=True or an explicit years_cap"):
        fetch_with_cache(
            "XAU/USD",
            "5m",
            max_history=False,
            years_cap=None,
            output_dir=tmp_path,
        )
