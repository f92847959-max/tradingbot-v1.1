"""Central data provider — unified interface for candle and indicator data."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from .broker_client import CapitalComClient
from .historical import get_latest_candles_from_db, download_historical_candles
from .indicators import calculate_indicators, get_indicator_summary
from shared.constants import TIMEFRAME_CANDLE_COUNTS

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)
_PANDAS = None


def _get_pandas():
    """Import pandas lazily so cold startup does not block on module import."""
    global _PANDAS
    if _PANDAS is None:
        import pandas as pd

        _PANDAS = pd
    return _PANDAS


class DataProvider:
    """Central data access for all modules needing market data."""

    # Minimum seconds between API fetches for the same timeframe
    _API_FETCH_COOLDOWN = 300  # 5 minutes

    def __init__(self, broker_client: CapitalComClient) -> None:
        self.client = broker_client
        self._last_api_fetch: dict[str, float] = {}

    async def get_candles_df(
        self,
        timeframe: str = "5m",
        count: int = 200,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """Get candles as DataFrame, optionally with indicators.

        Tries DB first, falls back to API if insufficient data.
        Avoids redundant API calls within a 5-minute cooldown window.
        """
        candles = await get_latest_candles_from_db(timeframe, count)

        if len(candles) < count:
            now = time.monotonic()
            last_fetch = self._last_api_fetch.get(timeframe, 0.0)
            if now - last_fetch >= self._API_FETCH_COOLDOWN:
                logger.info("DB has %d/%d candles for %s, fetching from API...",
                            len(candles), count, timeframe)
                await download_historical_candles(self.client, [timeframe], count)
                self._last_api_fetch[timeframe] = now
                candles = await get_latest_candles_from_db(timeframe, count)

        if not candles:
            pd = _get_pandas()
            return pd.DataFrame()

        pd = _get_pandas()
        df = pd.DataFrame(candles)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)

        if with_indicators and len(df) >= 20:
            df = calculate_indicators(df)

        return df

    async def get_current_price(self) -> dict:
        """Get current Gold bid/ask price."""
        return await self.client.get_current_price()

    async def get_indicator_summary(self, timeframe: str = "5m") -> dict:
        """Get latest indicator values as a dict summary."""
        count = TIMEFRAME_CANDLE_COUNTS.get(timeframe, 200)
        df = await self.get_candles_df(timeframe, count=count, with_indicators=True)
        if df.empty:
            return {}
        return get_indicator_summary(df)

    async def get_multi_timeframe_data(
        self, timeframes: list[str] | None = None, count: int | None = None
    ) -> dict[str, pd.DataFrame]:
        """Get candle DataFrames for multiple timeframes."""
        timeframes = timeframes or ["1m", "5m", "15m"]

        async def _fetch(tf: str):
            c = count if count is not None else TIMEFRAME_CANDLE_COUNTS.get(tf, 200)
            return tf, await self.get_candles_df(tf, c, with_indicators=True)

        results = await asyncio.gather(
            *[_fetch(tf) for tf in timeframes],
            return_exceptions=True,
        )
        out = {}
        for r in results:
            if isinstance(r, Exception):
                logger.warning("MTF fetch failed for one timeframe: %s", r)
                continue
            tf, df = r
            out[tf] = df
        return out
