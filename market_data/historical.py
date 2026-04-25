"""Load and store historical candle data from Capital.com."""

import logging

from .broker_client import CapitalComClient, CandleData
from database.connection import get_session
from database.repositories.candle_repo import CandleRepository

logger = logging.getLogger(__name__)

TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]

# Expected step in seconds per timeframe — used for gap detection
_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def _check_candle_gaps(candles: list[CandleData], timeframe: str) -> None:
    """Log a warning if candle timestamps are not contiguous for the timeframe."""
    expected = _TIMEFRAME_SECONDS.get(timeframe)
    if not expected or len(candles) < 2:
        return
    # Allow 50% slack to absorb weekends/market holidays without false positives
    threshold = expected * 1.5
    gaps = 0
    for prev, curr in zip(candles, candles[1:]):
        delta = (curr.timestamp - prev.timestamp).total_seconds()
        if delta > threshold:
            gaps += 1
    if gaps:
        logger.warning(
            "Detected %d non-contiguous gap(s) in %s candles (expected step ~%ds)",
            gaps, timeframe, expected,
        )


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
            if max_candles > 1000:
                candles = await client.get_candles_paginated(
                    timeframe=tf, total_count=max_candles,
                )
            else:
                candles = await client.get_candles(timeframe=tf, count=max_candles)

            if not candles:
                logger.warning("No candles returned for %s", tf)
                results[tf] = 0
                continue

            _check_candle_gaps(candles, tf)

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
