"""Trading rules engine based on economic calendar events.

Pure logic module -- no DB, no async.  Takes a list of EconomicEvent and
current time, returns trading decisions.

Rules:
- Pre-event block: No new trades within ``block_minutes_before`` of HIGH-impact event
- Post-event cooldown: No new trades within ``cooldown_minutes_after`` of HIGH-impact event
- Force close: EXTREME event (HIGH + USD) imminent within ``force_close_minutes_before``
- Medium impact: informational only (not a full block)
"""

import logging
from datetime import datetime, timedelta, timezone

from calendar.models import EconomicEvent, EventImpact

logger = logging.getLogger(__name__)


class EventRules:
    """Trading rules based on economic calendar events."""

    def __init__(
        self,
        block_minutes_before: int = 30,
        cooldown_minutes_after: int = 15,
        force_close_enabled: bool = True,
        force_close_minutes_before: int = 5,
    ) -> None:
        self.block_minutes_before = block_minutes_before
        self.cooldown_minutes_after = cooldown_minutes_after
        self.force_close_enabled = force_close_enabled
        self.force_close_minutes_before = force_close_minutes_before

    def is_high_impact_window(
        self,
        events: list[EconomicEvent],
        now: datetime | None = None,
    ) -> bool:
        """Return True if we are within a high-impact event window (block zone).

        Window = [event_time - block_minutes_before, event_time + cooldown_minutes_after]
        """
        if now is None:
            now = datetime.now(timezone.utc)

        for event in events:
            if event.impact != EventImpact.HIGH:
                continue
            window_start = event.event_time - timedelta(
                minutes=self.block_minutes_before
            )
            window_end = event.event_time + timedelta(
                minutes=self.cooldown_minutes_after
            )
            if window_start <= now <= window_end:
                logger.info(
                    "High-impact window active: '%s' at %s "
                    "(block %d min before, %d min after)",
                    event.title,
                    event.event_time.isoformat(),
                    self.block_minutes_before,
                    self.cooldown_minutes_after,
                )
                return True
        return False

    def should_force_close(
        self,
        events: list[EconomicEvent],
        now: datetime | None = None,
    ) -> bool:
        """Return True if positions should be force-closed due to imminent extreme event.

        Only triggers for EXTREME events (HIGH impact + USD) within
        ``force_close_minutes_before``.
        """
        if not self.force_close_enabled:
            return False

        if now is None:
            now = datetime.now(timezone.utc)

        for event in events:
            if not event.is_extreme:
                continue
            time_until = (event.event_time - now).total_seconds() / 60.0
            if 0 < time_until <= self.force_close_minutes_before:
                logger.warning(
                    "FORCE CLOSE triggered: extreme event '%s' in %.1f minutes",
                    event.title,
                    time_until,
                )
                return True
        return False

    def get_blocking_event(
        self,
        events: list[EconomicEvent],
        now: datetime | None = None,
    ) -> EconomicEvent | None:
        """Return the event causing a block, or None if no block."""
        if now is None:
            now = datetime.now(timezone.utc)

        for event in events:
            if event.impact != EventImpact.HIGH:
                continue
            window_start = event.event_time - timedelta(
                minutes=self.block_minutes_before
            )
            window_end = event.event_time + timedelta(
                minutes=self.cooldown_minutes_after
            )
            if window_start <= now <= window_end:
                return event
        return None
