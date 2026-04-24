"""yfinance batch fetcher with monotonic TTL cache (Phase 12, CORR-01).

Pattern source: .planning/phases/12-korrelations-engine/12-RESEARCH.md (Pattern 2).
Mirrors MiroFishClient TTL cache style using time.monotonic for clock-jump safety.
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd

try:
    import yfinance as yf
except ModuleNotFoundError:
    class _MissingYFinance:
        def download(self, *args, **kwargs):
            raise ModuleNotFoundError("No module named 'yfinance'")

    yf = _MissingYFinance()


TICKERS = {
    "dxy":   "DX-Y.NYB",
    "us10y": "^TNX",
    "silver": "SI=F",
    "vix":   "^VIX",
    "sp500": "^GSPC",
    "gold":  "GC=F",
}


class AssetFetcher:
    """Batch downloader for the 6 inter-market tickers used by the correlation engine.

    Returns a single DataFrame indexed by naive UTC dates (tz stripped) with internal
    column names {dxy, us10y, silver, vix, sp500, gold}. A monotonic-clock TTL cache
    avoids hammering yfinance (RESEARCH Pitfall 3: rate limits).
    """

    def __init__(self, cache_ttl_seconds: float = 3600.0) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._cached_df: Optional[pd.DataFrame] = None
        self._cache_ts: float = 0.0
        self._cache_lookback_days: Optional[int] = None

    def fetch_daily_closes(self, lookback_days: int = 200) -> pd.DataFrame:
        """Return DataFrame[date, dxy, us10y, silver, vix, sp500, gold] in naive UTC."""
        age = time.monotonic() - self._cache_ts
        if (
            self._cached_df is not None
            and self._cache_lookback_days == lookback_days
            and age < self._cache_ttl
        ):
            return self._cached_df

        raw = yf.download(
            " ".join(TICKERS.values()),
            period=f"{lookback_days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
            multi_level_index=True,
        )
        closes = raw["Close"].copy()
        reverse = {v: k for k, v in TICKERS.items()}
        closes = closes.rename(columns=reverse)
        # yfinance often returns tz-aware indexes; convert to naive UTC.
        idx = pd.to_datetime(closes.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        closes.index = idx
        closes = closes.dropna(how="all")

        self._cached_df = closes
        self._cache_ts = time.monotonic()
        self._cache_lookback_days = lookback_days
        return closes
