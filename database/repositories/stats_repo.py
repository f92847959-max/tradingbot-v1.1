"""Repository for portfolio statistics and equity curve."""

from datetime import date, datetime, timedelta
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import DailyStats, EquityCurve


class StatsRepository(BaseRepository[DailyStats]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DailyStats)

    async def get_by_date(self, d: date) -> DailyStats | None:
        stmt = select(DailyStats).where(DailyStats.date == d)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_range(self, start: date, end: date) -> Sequence[DailyStats]:
        stmt = (
            select(DailyStats)
            .where(and_(DailyStats.date >= start, DailyStats.date <= end))
            .order_by(DailyStats.date.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert(self, stats: dict) -> None:
        stmt = pg_insert(DailyStats).values(**stats)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            set_={k: v for k, v in stats.items() if k != "date"},
        )
        await self.session.execute(stmt)


class EquityCurveRepository(BaseRepository[EquityCurve]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EquityCurve)

    async def get_latest(self, days: int = 30) -> Sequence[EquityCurve]:
        cutoff = datetime.utcnow() - timedelta(days=days)
        stmt = (
            select(EquityCurve)
            .where(EquityCurve.timestamp >= cutoff)
            .order_by(EquityCurve.timestamp.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_point(self, equity: float, trade_id: int | None = None) -> EquityCurve:
        point = EquityCurve(
            timestamp=datetime.utcnow(),
            equity=equity,
            trade_id=trade_id,
        )
        return await self.add(point)
