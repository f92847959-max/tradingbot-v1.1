"""Unit tests for correlation.asset_fetcher.AssetFetcher (Phase 12, CORR-01).

Mocks yfinance.download to validate:
- batch download of all 6 TICKERS, renamed to internal column names
- naive datetime index (tz stripped)
- TTL cache: same DataFrame returned within window
- TTL expiry: re-fetch when monotonic clock past TTL
- all-NaN row dropping
- lookback_days propagated as period="{N}d", interval="1d"
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest


# Internal column names produced by AssetFetcher after renaming.
_INTERNAL_COLS = ["dxy", "us10y", "silver", "vix", "sp500", "gold"]
# Raw yfinance ticker symbols (must match TICKERS dict in asset_fetcher).
_RAW_TICKERS = ["DX-Y.NYB", "^TNX", "SI=F", "^VIX", "^GSPC", "GC=F"]


def _make_mock_download_df(periods: int = 30, tz: str | None = "America/New_York") -> pd.DataFrame:
    """Build a MultiIndex(Close, ticker) DataFrame mimicking yf.download output."""
    idx = pd.date_range("2026-01-01", periods=periods, freq="D", tz=tz)
    cols = pd.MultiIndex.from_product([["Close"], _RAW_TICKERS])
    rng = np.random.default_rng(42)
    return pd.DataFrame(rng.random((periods, 6)), index=idx, columns=cols)


def test_fetch_returns_all_assets():
    """fetch_daily_closes returns DataFrame[date, dxy, us10y, silver, vix, sp500, gold] in naive UTC."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df()
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df) as mock_dl:
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        result = fetcher.fetch_daily_closes(lookback_days=30)

    assert mock_dl.call_count == 1
    assert sorted(result.columns.tolist()) == sorted(_INTERNAL_COLS)
    # Index must be naive (tz stripped)
    assert result.index.tz is None


def test_cache_ttl():
    """Two sequential calls within TTL return the SAME DataFrame; yf.download called once."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df()
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df) as mock_dl, \
         patch("correlation.asset_fetcher.time.monotonic", side_effect=[0.0, 10.0, 100.0]):
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        first = fetcher.fetch_daily_closes(lookback_days=30)
        second = fetcher.fetch_daily_closes(lookback_days=30)

    assert mock_dl.call_count == 1
    assert first is second


def test_cache_expiry():
    """When monotonic clock exceeds TTL, second call re-fetches."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df()
    # monotonic sequence:
    #   t=0.0  -> initial age computation (cache miss path)
    #   t=10.0 -> stamp first cache
    #   t=7200 -> age check for second call (> 3600 ttl, expired)
    #   t=7210 -> stamp refreshed cache
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df) as mock_dl, \
         patch("correlation.asset_fetcher.time.monotonic",
               side_effect=[0.0, 10.0, 7200.0, 7210.0]):
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        fetcher.fetch_daily_closes(lookback_days=30)
        fetcher.fetch_daily_closes(lookback_days=30)

    assert mock_dl.call_count == 2


def test_drops_all_nan_rows():
    """Rows that are entirely NaN across all tickers are dropped."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df(periods=10)
    # Insert an all-NaN row at index 5
    mock_df.iloc[5, :] = np.nan
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df):
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        result = fetcher.fetch_daily_closes(lookback_days=10)

    assert len(result) == 9  # one row dropped
    assert not result.isna().all(axis=1).any()


def test_lookback_days_passed():
    """lookback_days is propagated as period=\"{N}d\" and interval=\"1d\" to yf.download."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df()
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df) as mock_dl:
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        fetcher.fetch_daily_closes(lookback_days=200)

    _, kwargs = mock_dl.call_args
    assert kwargs.get("period") == "200d"
    assert kwargs.get("interval") == "1d"


def test_cache_bypassed_when_lookback_changes():
    """Changing lookback_days must bypass the TTL cache."""
    from correlation.asset_fetcher import AssetFetcher

    mock_df = _make_mock_download_df()
    with patch("correlation.asset_fetcher.yf.download", return_value=mock_df) as mock_dl, \
         patch("correlation.asset_fetcher.time.monotonic", side_effect=[0.0, 10.0, 20.0, 30.0]):
        fetcher = AssetFetcher(cache_ttl_seconds=3600)
        fetcher.fetch_daily_closes(lookback_days=30)
        fetcher.fetch_daily_closes(lookback_days=200)

    assert mock_dl.call_count == 2
