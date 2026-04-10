"""Database persistence for economic calendar events."""

import logging
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import EconomicEventRecord
from database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EventRepository(BaseRepository[EconomicEventRecord]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, EconomicEventRecord)

    async def get_upcoming(
        self, from_time: datetime, hours: int = 24
    ) -> Sequence[EconomicEventRecord]:
        """Get events in the next N hours from from_time."""
        until = from_time + timedelta(hours=hours)
        stmt = (
            select(EconomicEventRecord)
            .where(EconomicEventRecord.event_time >= from_time)
            .where(EconomicEventRecord.event_time <= until)
            .order_by(EconomicEventRecord.event_time.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_by_date_range(
        self, start: datetime, end: datetime
    ) -> Sequence[EconomicEventRecord]:
        """Get events between start and end (for backtesting -- ECAL-04)."""
        stmt = (
            select(EconomicEventRecord)
            .where(EconomicEventRecord.event_time >= start)
            .where(EconomicEventRecord.event_time <= end)
            .order_by(EconomicEventRecord.event_time.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert_events(self, events: list[EconomicEventRecord]) -> int:
        """Insert events, skip duplicates (title + event_time unique).

        Returns count of successfully inserted events.
        """
        inserted = 0
        for event in events:
            # Check if event already exists (unique on title + event_time)
            stmt = (
                select(EconomicEventRecord)
                .where(EconomicEventRecord.title == event.title)
                .where(EconomicEventRecord.event_time == event.event_time)
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is None:
                self.session.add(event)
                inserted += 1
            else:
                # Update actual value if it has changed
                if event.actual and existing.actual != event.actual:
                    existing.actual = event.actual

        if inserted > 0:
            await self.session.flush()
            logger.info("Inserted %d new economic events", inserted)

        return inserted

    async def get_high_impact_in_window(
        self,
        center_time: datetime,
        minutes_before: int = 30,
        minutes_after: int = 15,
    ) -> Sequence[EconomicEventRecord]:
        """Get high-impact events within a time window around center_time."""
        window_start = center_time - timedelta(minutes=minutes_before)
        window_end = center_time + timedelta(minutes=minutes_after)
        stmt = (
            select(EconomicEventRecord)
            .where(EconomicEventRecord.impact == "high")
            .where(EconomicEventRecord.event_time >= window_start)
            .where(EconomicEventRecord.event_time <= window_end)
            .order_by(EconomicEventRecord.event_time.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
