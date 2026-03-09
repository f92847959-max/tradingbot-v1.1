"""Repository for candle data operations."""

import logging
from datetime import datetime
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import Candle

logger = logging.getLogger(__name__)


class CandleRepository(BaseRepository[Candle]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Candle)

    async def get_latest(
        self, timeframe: str, count: int = 200
    ) -> Sequence[Candle]:
        stmt = (
            select(Candle)
            .where(Candle.timeframe == timeframe)
            .order_by(Candle.timestamp.desc())
            .limit(count)
        )
        result = await self.session.execute(stmt)
        return list(reversed(result.scalars().all()))

    async def get_range(
        self, timeframe: str, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        stmt = (
            select(Candle)
            .where(
                and_(
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= start,
                    Candle.timestamp <= end,
                )
            )
            .order_by(Candle.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert(self, candle: Candle) -> None:
        """Insert or update candle (conflict on timestamp+timeframe)."""
        stmt = pg_insert(Candle).values(
            timestamp=candle.timestamp,
            timeframe=candle.timeframe,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            spread=candle.spread,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["timestamp", "timeframe"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "spread": stmt.excluded.spread,
            },
        )
        await self.session.execute(stmt)

    async def upsert_many(self, candles: list[dict]) -> int:
        """Bulk upsert candles from list of dicts."""
        if not candles:
            return 0
        stmt = pg_insert(Candle).values(candles)
        stmt = stmt.on_conflict_do_update(
            index_elements=["timestamp", "timeframe"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "spread": stmt.excluded.spread,
            },
        )
        await self.session.execute(stmt)
        return len(candles)

    async def get_last_timestamp(self, timeframe: str) -> datetime | None:
        from sqlalchemy import func
        stmt = (
            select(func.max(Candle.timestamp))
            .where(Candle.timeframe == timeframe)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_older_than(self, days: int) -> int:
        """Delete candles older than the given number of days.

        Returns the count of deleted rows.
        """
        from datetime import timedelta, timezone
        from sqlalchemy import delete, func

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            delete(Candle)
            .where(Candle.timestamp < cutoff)
        )
        result = await self.session.execute(stmt)
        deleted = result.rowcount
        if deleted:
            logger.info("Candle retention: deleted %d candles older than %d days", deleted, days)
        return deleted
