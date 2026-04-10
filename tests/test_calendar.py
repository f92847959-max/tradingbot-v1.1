"""Unit tests for calendar/ module: models, rules, filter, service."""

import pytest
from datetime import datetime, timedelta, timezone

from calendar.models import EconomicEvent, EventImpact
from calendar.event_rules import EventRules
from calendar.event_filter import filter_gold_relevant


# -- Model tests --

class TestEconomicEvent:
    def test_event_impact_enum(self):
        assert EventImpact.LOW.value == "low"
        assert EventImpact.MEDIUM.value == "medium"
        assert EventImpact.HIGH.value == "high"

    def test_is_high_impact(self):
        e = EconomicEvent(title="NFP", country="USD", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))
        assert e.is_high_impact is True

    def test_is_not_high_impact(self):
        e = EconomicEvent(title="PMI", country="EUR", impact=EventImpact.MEDIUM, event_time=datetime.now(timezone.utc))
        assert e.is_high_impact is False

    def test_is_extreme_usd_high(self):
        e = EconomicEvent(title="FOMC", country="USD", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))
        assert e.is_extreme is True

    def test_is_not_extreme_eur_high(self):
        e = EconomicEvent(title="ECB Rate", country="EUR", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))
        assert e.is_extreme is False

    def test_is_not_extreme_usd_medium(self):
        e = EconomicEvent(title="ISM PMI", country="USD", impact=EventImpact.MEDIUM, event_time=datetime.now(timezone.utc))
        assert e.is_extreme is False

    def test_is_not_extreme_usd_low(self):
        e = EconomicEvent(title="Redbook", country="USD", impact=EventImpact.LOW, event_time=datetime.now(timezone.utc))
        assert e.is_extreme is False


# -- EventRules tests --

class TestEventRules:
    @pytest.fixture
    def rules(self):
        return EventRules(block_minutes_before=30, cooldown_minutes_after=15)

    @pytest.fixture
    def nfp_event(self):
        return EconomicEvent(
            title="Non-Farm Payrolls",
            country="USD",
            impact=EventImpact.HIGH,
            event_time=datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc),
        )

    def test_high_impact_window_inside_before(self, rules, nfp_event):
        """10 min before HIGH event = inside window."""
        now = nfp_event.event_time - timedelta(minutes=10)
        assert rules.is_high_impact_window([nfp_event], now=now) is True

    def test_high_impact_window_outside_before(self, rules, nfp_event):
        """60 min before HIGH event = outside window."""
        now = nfp_event.event_time - timedelta(minutes=60)
        assert rules.is_high_impact_window([nfp_event], now=now) is False

    def test_high_impact_window_inside_cooldown(self, rules, nfp_event):
        """5 min after HIGH event = inside cooldown."""
        now = nfp_event.event_time + timedelta(minutes=5)
        assert rules.is_high_impact_window([nfp_event], now=now) is True

    def test_high_impact_window_outside_cooldown(self, rules, nfp_event):
        """30 min after HIGH event = outside cooldown."""
        now = nfp_event.event_time + timedelta(minutes=30)
        assert rules.is_high_impact_window([nfp_event], now=now) is False

    def test_high_impact_window_medium_ignored(self, rules):
        """Medium impact events do NOT trigger the window."""
        event = EconomicEvent(
            title="PMI", country="USD", impact=EventImpact.MEDIUM,
            event_time=datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc),
        )
        now = event.event_time - timedelta(minutes=10)
        assert rules.is_high_impact_window([event], now=now) is False

    def test_high_impact_window_low_ignored(self, rules):
        """Low impact events do NOT trigger the window."""
        event = EconomicEvent(
            title="Redbook", country="USD", impact=EventImpact.LOW,
            event_time=datetime(2025, 1, 10, 14, 0, tzinfo=timezone.utc),
        )
        now = event.event_time - timedelta(minutes=10)
        assert rules.is_high_impact_window([event], now=now) is False

    def test_force_close_imminent_extreme(self, rules, nfp_event):
        """3 min before extreme event -> force close."""
        now = nfp_event.event_time - timedelta(minutes=3)
        assert rules.should_force_close([nfp_event], now=now) is True

    def test_force_close_not_imminent(self, rules, nfp_event):
        """20 min before extreme event -> no force close."""
        now = nfp_event.event_time - timedelta(minutes=20)
        assert rules.should_force_close([nfp_event], now=now) is False

    def test_force_close_non_usd_high(self, rules):
        """3 min before HIGH EUR event -> NOT extreme, no force close."""
        ecb = EconomicEvent(
            title="ECB Rate Decision", country="EUR", impact=EventImpact.HIGH,
            event_time=datetime(2025, 1, 10, 13, 45, tzinfo=timezone.utc),
        )
        now = ecb.event_time - timedelta(minutes=3)
        assert rules.should_force_close([ecb], now=now) is False

    def test_force_close_disabled(self):
        """force_close_enabled=False -> always False."""
        rules = EventRules(force_close_enabled=False)
        nfp = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc),
        )
        now = nfp.event_time - timedelta(minutes=2)
        assert rules.should_force_close([nfp], now=now) is False

    def test_force_close_after_event_no_trigger(self, rules, nfp_event):
        """Force close only triggers BEFORE the event, not after."""
        now = nfp_event.event_time + timedelta(minutes=1)
        assert rules.should_force_close([nfp_event], now=now) is False

    def test_get_blocking_event_returns_event(self, rules, nfp_event):
        now = nfp_event.event_time - timedelta(minutes=10)
        result = rules.get_blocking_event([nfp_event], now=now)
        assert result is not None
        assert result.title == "Non-Farm Payrolls"

    def test_get_blocking_event_returns_none(self, rules, nfp_event):
        now = nfp_event.event_time - timedelta(minutes=60)
        assert rules.get_blocking_event([nfp_event], now=now) is None

    def test_empty_events_no_block(self, rules):
        assert rules.is_high_impact_window([], now=datetime.now(timezone.utc)) is False
        assert rules.should_force_close([], now=datetime.now(timezone.utc)) is False

    def test_multiple_events_first_blocking(self, rules):
        """When multiple events exist, first blocking one is returned."""
        now = datetime(2025, 1, 10, 13, 25, tzinfo=timezone.utc)
        e1 = EconomicEvent(
            title="CPI", country="USD", impact=EventImpact.HIGH,
            event_time=datetime(2025, 1, 10, 13, 30, tzinfo=timezone.utc),
        )
        e2 = EconomicEvent(
            title="PMI", country="EUR", impact=EventImpact.HIGH,
            event_time=datetime(2025, 1, 10, 15, 0, tzinfo=timezone.utc),
        )
        result = rules.get_blocking_event([e1, e2], now=now)
        assert result is not None
        assert result.title == "CPI"


# -- Filter tests --

class TestEventFilter:
    def test_keeps_usd_high(self):
        events = [EconomicEvent(title="NFP", country="USD", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_keeps_eur_high(self):
        events = [EconomicEvent(title="ECB Rate", country="EUR", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_drops_low_non_gold_country(self):
        events = [EconomicEvent(title="Building Permits", country="AUD", impact=EventImpact.LOW, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 0

    def test_keeps_low_with_gold_keyword(self):
        events = [EconomicEvent(title="COMEX Gold Inventory", country="USD", impact=EventImpact.LOW, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_drops_non_relevant_country_medium(self):
        events = [EconomicEvent(title="Trade Balance", country="NZD", impact=EventImpact.MEDIUM, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 0

    def test_keeps_jpn_medium(self):
        events = [EconomicEvent(title="BOJ Rate", country="JPY", impact=EventImpact.MEDIUM, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_keeps_gbp_high(self):
        events = [EconomicEvent(title="BOE Rate Decision", country="GBP", impact=EventImpact.HIGH, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_keeps_chf_medium(self):
        events = [EconomicEvent(title="SNB Rate", country="CHF", impact=EventImpact.MEDIUM, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 1

    def test_drops_aud_low(self):
        events = [EconomicEvent(title="Employment Change", country="AUD", impact=EventImpact.LOW, event_time=datetime.now(timezone.utc))]
        assert len(filter_gold_relevant(events)) == 0


# -- EventService tests (unit-level, no DB) --

class TestEventService:
    def test_is_high_impact_window_with_no_events(self):
        from calendar.event_service import EventService
        service = EventService()
        assert service.is_high_impact_window() is False

    def test_should_force_close_with_no_events(self):
        from calendar.event_service import EventService
        service = EventService()
        assert service.should_force_close() is False

    def test_get_upcoming_events_empty(self):
        from calendar.event_service import EventService
        service = EventService()
        assert service.get_upcoming_events(hours=24) == []

    def test_cached_event_count_zero(self):
        from calendar.event_service import EventService
        service = EventService()
        assert service.cached_event_count == 0

    def test_is_high_impact_window_with_cached_events(self):
        """Manually populate cache and test window logic."""
        from calendar.event_service import EventService
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        # Inject a HIGH event 10 minutes from now
        event = EconomicEvent(
            title="CPI", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        service._cached_events = [event]
        assert service.is_high_impact_window() is True

    def test_custom_minutes_before_override(self):
        from calendar.event_service import EventService
        service = EventService(block_minutes_before=30)
        # Event 40 min from now: default 30 min window should NOT block
        event = EconomicEvent(
            title="FOMC", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=40),
        )
        service._cached_events = [event]
        assert service.is_high_impact_window() is False
        # But 60 min custom window SHOULD block
        assert service.is_high_impact_window(minutes_before=60) is True

    def test_get_blocking_event_with_cache(self):
        from calendar.event_service import EventService
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        event = EconomicEvent(
            title="NFP", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        service._cached_events = [event]
        blocking = service.get_blocking_event()
        assert blocking is not None
        assert blocking.title == "NFP"

    def test_get_blocking_event_none_when_clear(self):
        from calendar.event_service import EventService
        service = EventService(block_minutes_before=30, cooldown_minutes_after=15)
        event = EconomicEvent(
            title="FOMC", country="USD", impact=EventImpact.HIGH,
            event_time=datetime.now(timezone.utc) + timedelta(hours=5),
        )
        service._cached_events = [event]
        assert service.get_blocking_event() is None

    def test_last_refresh_initially_none(self):
        from calendar.event_service import EventService
        service = EventService()
        assert service.last_refresh is None
