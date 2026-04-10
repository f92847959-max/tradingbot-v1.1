"""Economic calendar service -- shared interface for trading system.

Phase 9 (risk) and Phase 10 (exits) import from here::

    from calendar.event_service import EventService

    service = EventService()
    await service.refresh()
    service.is_high_impact_window()
    service.should_force_close()
    service.get_upcoming_events(hours=24)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Sequence

from calendar.models import EconomicEvent, EventImpact
from calendar.event_rules import EventRules

logger = logging.getLogger(__name__)


class EventService:
    """Facade for economic calendar functionality.

    Usage::

        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        await service.refresh()  # Fetch + filter + store events
        if service.is_high_impact_window():
            # Block new trades
        if service.should_force_close():
            # Close all positions
    """

    def __init__(
        self,
        block_minutes_before: int = 30,
        cooldown_minutes_after: int = 15,
        force_close_enabled: bool = True,
        force_close_minutes_before: int = 5,
    ) -> None:
        self._rules = EventRules(
            block_minutes_before=block_minutes_before,
            cooldown_minutes_after=cooldown_minutes_after,
            force_close_enabled=force_close_enabled,
            force_close_minutes_before=force_close_minutes_before,
        )
        self._cached_events: list[EconomicEvent] = []
        self._last_refresh: datetime | None = None

    async def refresh(self) -> int:
        """Fetch events from ForexFactory, filter for Gold relevance, store in DB.

        Returns count of new events stored.
        """
        from calendar.event_fetcher import fetch_events_this_week
        from calendar.event_filter import filter_gold_relevant
        from database.connection import get_session
        from database.models import EconomicEventRecord
        from calendar.event_repository import EventRepository

        raw_events = await fetch_events_this_week()
        filtered = filter_gold_relevant(raw_events)

        # Convert domain objects to ORM records and persist
        records: list[EconomicEventRecord] = []
        for e in filtered:
            records.append(
                EconomicEventRecord(
                    title=e.title,
                    country=e.country,
                    impact=e.impact.value,
                    event_time=e.event_time,
                    forecast=e.forecast,
                    previous=e.previous,
                    actual=e.actual,
                )
            )

        stored = 0
        if records:
            async with get_session() as session:
                repo = EventRepository(session)
                stored = await repo.upsert_events(records)

        # Update in-memory cache
        self._cached_events = filtered
        self._last_refresh = datetime.now(timezone.utc)
        logger.info(
            "Calendar refresh: %d fetched, %d Gold-relevant, %d new stored",
            len(raw_events),
            len(filtered),
            stored,
        )
        return stored

    def is_high_impact_window(self, minutes_before: int | None = None) -> bool:
        """Check if current time is in a high-impact event window.

        Args:
            minutes_before: Override block window. If None, uses configured default.
        """
        if minutes_before is not None:
            # Create temporary rules with custom window
            rules = EventRules(
                block_minutes_before=minutes_before,
                cooldown_minutes_after=self._rules.cooldown_minutes_after,
            )
            return rules.is_high_impact_window(self._cached_events)
        return self._rules.is_high_impact_window(self._cached_events)

    def should_force_close(self) -> bool:
        """Check if positions should be force-closed due to imminent extreme event."""
        return self._rules.should_force_close(self._cached_events)

    def get_upcoming_events(self, hours: int = 24) -> list[EconomicEvent]:
        """Get upcoming events within the next N hours."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        return [e for e in self._cached_events if now <= e.event_time <= cutoff]

    def get_blocking_event(self) -> EconomicEvent | None:
        """Get the specific event causing a trade block, or None."""
        return self._rules.get_blocking_event(self._cached_events)

    @property
    def last_refresh(self) -> datetime | None:
        return self._last_refresh

    @property
    def cached_event_count(self) -> int:
        return len(self._cached_events)
