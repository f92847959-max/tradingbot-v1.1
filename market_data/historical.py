"""Load and store historical candle data from Capital.com."""

import logging
from datetime import datetime, timedelta

from .broker_client import CapitalComClient, CandleData
from database.connection import get_session
from database.repositories.candle_repo import CandleRepository

logger = logging.getLogger(__name__)

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]


async def download_historical_candles(
    client: CapitalComClient,
    timeframes: list[str] | None = None,
    max_candles: int = 1000,
) -> dict[str, int]:
    """Download historical candles for all timeframes and store in DB.

    Returns dict of {timeframe: count_stored}.
    """
    timeframes = timeframes or ["1m", "5m", "15m"]
    results = {}

    for tf in timeframes:
        try:
            logger.info("Downloading %s candles (max %d)...", tf, max_candles)
            candles = await client.get_candles(timeframe=tf, count=max_candles)

            if not candles:
                logger.warning("No candles returned for %s", tf)
                results[tf] = 0
                continue

            # Convert to dicts for bulk upsert
            candle_dicts = [
                {
                    "timestamp": c.timestamp,
                    "timeframe": tf,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "spread": None,
                }
                for c in candles
            ]

            async with get_session() as session:
                repo = CandleRepository(session)
                count = await repo.upsert_many(candle_dicts)
                results[tf] = count

            logger.info("Stored %d candles for %s (range: %s to %s)",
                        len(candles), tf,
                        candles[0].timestamp.isoformat(),
                        candles[-1].timestamp.isoformat())

        except Exception as e:
            logger.error("Failed to download %s candles: %s", tf, e)
            results[tf] = 0

    return results


async def get_latest_candles_from_db(
    timeframe: str, count: int = 200
) -> list[dict]:
    """Retrieve latest candles from database as list of dicts."""
    async with get_session() as session:
        repo = CandleRepository(session)
        candles = await repo.get_latest(timeframe, count)
        return [
            {
                "timestamp": c.timestamp,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": float(c.volume) if c.volume else 0.0,
            }
            for c in candles
        ]
