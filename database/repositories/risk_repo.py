"""Repository for risk events and daily risk state."""

from datetime import date, datetime, timedelta
from typing import Sequence

from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .base import BaseRepository
from ..models import RiskEvent, DailyRiskState


class RiskRepository(BaseRepository[RiskEvent]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, RiskEvent)

    async def log_event(
        self, event_type: str, message: str, details: dict | None = None
    ) -> RiskEvent:
        event = RiskEvent(
            event_type=event_type,
            message=message,
            details=details,
        )
        return await self.add(event)

    async def get_recent(self, hours: int = 24) -> Sequence[RiskEvent]:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        stmt = (
            select(RiskEvent)
            .where(RiskEvent.timestamp >= cutoff)
            .order_by(RiskEvent.timestamp.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_type(
        self, event_type: str, limit: int = 50
    ) -> Sequence[RiskEvent]:
        stmt = (
            select(RiskEvent)
            .where(RiskEvent.event_type == event_type)
            .order_by(RiskEvent.timestamp.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


class DailyRiskStateRepository(BaseRepository[DailyRiskState]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, DailyRiskState)

    async def get_today(self) -> DailyRiskState | None:
        stmt = select(DailyRiskState).where(DailyRiskState.date == date.today())
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_today(self, state: dict) -> None:
        state["date"] = date.today()
        stmt = pg_insert(DailyRiskState).values(**state)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            set_={k: v for k, v in state.items() if k != "date"},
        )
        await self.session.execute(stmt)

    async def is_kill_switch_active(self) -> bool:
        today = await self.get_today()
        if today is None:
            return False
        return today.kill_switch_activated

    async def activate_kill_switch(self) -> None:
        await self.upsert_today({"kill_switch_activated": True})

    async def deactivate_kill_switch(self) -> None:
        await self.upsert_today({"kill_switch_activated": False})
