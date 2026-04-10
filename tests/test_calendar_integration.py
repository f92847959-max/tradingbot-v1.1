"""Integration tests: calendar event veto in trading system."""

import pytest
from datetime import datetime, timedelta, timezone

from calendar.models import EconomicEvent, EventImpact
from calendar.event_service import EventService


class TestTradingLoopCalendarVeto:
    """Test that trading_loop.py respects calendar event windows."""

    def test_event_service_blocks_during_window(self):
        """EventService.is_high_impact_window blocks when event is near."""
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        nfp = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        service._cached_events = [nfp]
        assert service.is_high_impact_window() is True, "Should block 15 min before NFP"

    def test_event_service_allows_when_clear(self):
        """EventService allows trading when no events are near."""
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        nfp = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(hours=5),
        )
        service._cached_events = [nfp]
        assert service.is_high_impact_window() is False, "Should allow trading 5h before NFP"

    def test_force_close_triggers_for_extreme(self):
        """Force-close triggers when extreme event is imminent."""
        service = EventService(force_close_enabled=True, force_close_minutes_before=5)
        nfp = EconomicEvent(
            title="Non-Farm Payrolls", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=3),
        )
        service._cached_events = [nfp]
        assert service.should_force_close() is True

    def test_no_force_close_for_non_extreme(self):
        """Non-extreme events (EUR HIGH) do NOT trigger force-close."""
        service = EventService(force_close_enabled=True, force_close_minutes_before=5)
        ecb = EconomicEvent(
            title="ECB Rate Decision", country="EUR", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=3),
        )
        service._cached_events = [ecb]
        assert service.should_force_close() is False

    def test_disabled_calendar_returns_false(self):
        """When calendar is effectively empty, all checks return False."""
        service = EventService()
        # No events loaded
        assert service.is_high_impact_window() is False
        assert service.should_force_close() is False
        assert service.get_upcoming_events() == []

    def test_get_upcoming_events_filters_by_hours(self):
        """get_upcoming_events only returns events within the specified window."""
        service = EventService()
        now = datetime.now(timezone.utc)
        service._cached_events = [
            EconomicEvent(title="Soon", country="USD", impact=EventImpact.HIGH, event_time=now + timedelta(hours=2)),
            EconomicEvent(title="Far", country="USD", impact=EventImpact.HIGH, event_time=now + timedelta(hours=48)),
            EconomicEvent(title="Past", country="USD", impact=EventImpact.HIGH, event_time=now - timedelta(hours=1)),
        ]
        upcoming = service.get_upcoming_events(hours=24)
        assert len(upcoming) == 1
        assert upcoming[0].title == "Soon"

    def test_force_close_with_force_close_disabled(self):
        """When force_close_enabled=False, should_force_close always returns False."""
        service = EventService(force_close_enabled=False)
        nfp = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=2),
        )
        service._cached_events = [nfp]
        assert service.should_force_close() is False

    def test_high_impact_window_during_cooldown(self):
        """EventService blocks during cooldown period after event."""
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        # Event happened 5 minutes ago
        nfp = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        service._cached_events = [nfp]
        assert service.is_high_impact_window() is True, "Should block during cooldown after NFP"

    def test_multiple_events_first_blocks(self):
        """With multiple events, the nearest one blocks."""
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        now = datetime.now(timezone.utc)
        service._cached_events = [
            EconomicEvent(title="CPI", country="USD", impact=EventImpact.HIGH,
                          event_time=now + timedelta(minutes=10)),
            EconomicEvent(title="GDP", country="USD", impact=EventImpact.HIGH,
                          event_time=now + timedelta(hours=3)),
        ]
        assert service.is_high_impact_window() is True
        blocking = service.get_blocking_event()
        assert blocking is not None
        assert blocking.title == "CPI"
