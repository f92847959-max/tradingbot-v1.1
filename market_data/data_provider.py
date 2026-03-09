"""Central data provider — unified interface for candle and indicator data."""

import logging
from datetime import datetime

import pandas as pd

from .broker_client import CapitalComClient
from .historical import get_latest_candles_from_db, download_historical_candles
from .indicators import calculate_indicators, get_indicator_summary
from database.connection import get_session
from database.repositories.candle_repo import CandleRepository

logger = logging.getLogger(__name__)


class DataProvider:
    """Central data access for all modules needing market data."""

    def __init__(self, broker_client: CapitalComClient) -> None:
        self.client = broker_client

    async def get_candles_df(
        self,
        timeframe: str = "5m",
        count: int = 200,
        with_indicators: bool = True,
    ) -> pd.DataFrame:
        """Get candles as DataFrame, optionally with indicators.

        Tries DB first, falls back to API if insufficient data.
        """
        candles = await get_latest_candles_from_db(timeframe, count)

        if len(candles) < count:
            logger.info("DB has %d/%d candles for %s, fetching from API...",
                        len(candles), count, timeframe)
            await download_historical_candles(self.client, [timeframe], count)
            candles = await get_latest_candles_from_db(timeframe, count)

        if not candles:
            return pd.DataFrame()

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
        df = await self.get_candles_df(timeframe, count=200, with_indicators=True)
        if df.empty:
            return {}
        return get_indicator_summary(df)

    async def get_multi_timeframe_data(
        self, timeframes: list[str] | None = None, count: int = 200
    ) -> dict[str, pd.DataFrame]:
        """Get candle DataFrames for multiple timeframes."""
        timeframes = timeframes or ["1m", "5m", "15m"]
        result = {}
        for tf in timeframes:
            result[tf] = await self.get_candles_df(tf, count, with_indicators=True)
        return result
