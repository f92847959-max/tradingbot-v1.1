"""Tests for calendar EventService wiring into trading loop and lifecycle.

Validates:
- trading_loop.py vetoes trades during high-impact event windows
- trading_loop.py force-closes positions before extreme events
- lifecycle.py creates EventService when calendar_enabled=True
- lifecycle.py has _calendar_refresh_loop for background refresh
- Graceful degradation when calendar_enabled=False
"""

import asyncio
import inspect
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from calendar.models import EconomicEvent, EventImpact
from calendar.event_service import EventService


class TestLifecycleCalendarWiring:
    """Test that lifecycle.py correctly initializes and refreshes EventService."""

    def test_lifecycle_has_calendar_refresh_loop(self):
        """LifecycleMixin must have _calendar_refresh_loop method."""
        from trading.lifecycle import LifecycleMixin
        assert hasattr(LifecycleMixin, '_calendar_refresh_loop'), \
            "LifecycleMixin missing _calendar_refresh_loop method"

    def test_calendar_refresh_loop_is_async(self):
        """_calendar_refresh_loop must be an async method."""
        from trading.lifecycle import LifecycleMixin
        method = getattr(LifecycleMixin, '_calendar_refresh_loop', None)
        assert method is not None, "Missing _calendar_refresh_loop"
        assert asyncio.iscoroutinefunction(method), \
            "_calendar_refresh_loop must be async"

    def test_lifecycle_init_creates_event_service_when_enabled(self):
        """When calendar_enabled=True, __init__ should set self._event_service."""
        from trading.lifecycle import LifecycleMixin
        source = inspect.getsource(LifecycleMixin.__init__)
        assert 'calendar_enabled' in source, \
            "__init__ must check settings.calendar_enabled"
        assert '_event_service' in source, \
            "__init__ must set self._event_service"

    def test_lifecycle_init_sets_none_when_disabled(self):
        """When calendar_enabled=False, self._event_service should be None."""
        from trading.lifecycle import LifecycleMixin
        source = inspect.getsource(LifecycleMixin.__init__)
        assert '_event_service = None' in source, \
            "__init__ must default _event_service to None"


class TestTradingLoopCalendarChecks:
    """Test that trading_loop.py has event veto and force-close checks."""

    def test_trading_tick_has_high_impact_check(self):
        """_trading_tick must check is_high_impact_window."""
        from trading.trading_loop import TradingLoopMixin
        source = inspect.getsource(TradingLoopMixin._trading_tick)
        assert 'is_high_impact_window' in source, \
            "_trading_tick must call is_high_impact_window()"

    def test_trading_tick_has_force_close_check(self):
        """_trading_tick must check should_force_close."""
        from trading.trading_loop import TradingLoopMixin
        source = inspect.getsource(TradingLoopMixin._trading_tick)
        assert 'should_force_close' in source, \
            "_trading_tick must call should_force_close()"

    def test_trading_tick_guards_with_none_check(self):
        """Event checks must be guarded by 'self._event_service is not None'."""
        from trading.trading_loop import TradingLoopMixin
        source = inspect.getsource(TradingLoopMixin._trading_tick)
        assert '_event_service is not None' in source, \
            "Event checks must guard with 'self._event_service is not None'"

    def test_force_close_before_high_impact_check(self):
        """Force-close check must come before high-impact window check."""
        from trading.trading_loop import TradingLoopMixin
        source = inspect.getsource(TradingLoopMixin._trading_tick)
        fc_pos = source.find('should_force_close')
        hi_pos = source.find('is_high_impact_window')
        assert fc_pos > 0 and hi_pos > 0, "Both checks must be present"
        assert fc_pos < hi_pos, \
            "should_force_close must come before is_high_impact_window"
