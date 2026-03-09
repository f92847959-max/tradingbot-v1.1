"""Unit tests for the trailing stop manager."""

import pytest
from dataclasses import dataclass
from typing import Optional

from order_management.trailing_stop import TrailingStopManager
from market_data.broker_client import Position


def make_position(
    deal_id: str = "TEST001",
    direction: str = "BUY",
    open_level: float = 2000.0,
    current_level: float = 2010.0,
    stop_level: Optional[float] = 1990.0,
) -> Position:
    return Position(
        deal_id=deal_id,
        direction=direction,
        size=1.0,
        open_level=open_level,
        current_level=current_level,
        stop_level=stop_level,
    )


class TestTrailingStopBuy:
    def _manager(self, activation=10.0, trail=5.0) -> TrailingStopManager:
        return TrailingStopManager(
            activation_pips=activation,
            trail_distance_pips=trail,
            pip_size=0.01,
        )

    def test_no_update_before_activation(self):
        """Trailing should not activate until profit >= activation_pips."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, current_level=2000.05)
        # Only 5 pips profit — activation requires 10
        result = mgr.calculate_new_sl(pos, current_price=2000.05)
        assert result is None

    def test_activates_at_threshold(self):
        """Trailing should activate once profit exceeds activation_pips."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, current_level=2000.15, stop_level=1990.0)
        # 15 pips profit (clear of float rounding around 10 pips)
        result = mgr.calculate_new_sl(pos, current_price=2000.15)
        assert result is not None

    def test_sl_moves_up_on_price_rise(self):
        """For BUY, SL should move up as price rises."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, stop_level=1990.0)

        # First update at 2000.20 (20 pips profit)
        result1 = mgr.calculate_new_sl(pos, current_price=2000.20)
        assert result1 is not None
        assert result1 > 1990.0  # SL moved up

        # Price rises further
        pos2 = make_position(direction="BUY", open_level=2000.0, stop_level=result1)
        result2 = mgr.calculate_new_sl(pos2, current_price=2000.40)
        assert result2 is not None
        assert result2 > result1  # SL moved up again

    def test_sl_does_not_move_down_on_price_drop(self):
        """For BUY, SL should NEVER move down."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, stop_level=1990.0)

        # First: establish trailing at high price
        result1 = mgr.calculate_new_sl(pos, current_price=2000.50)
        assert result1 is not None

        # Now price drops — SL should not move down
        pos2 = make_position(direction="BUY", open_level=2000.0, stop_level=result1)
        result2 = mgr.calculate_new_sl(pos2, current_price=2000.20)
        assert result2 is None  # No update — price dropped

    def test_trailing_distance_correct(self):
        """SL should be exactly trail_distance behind current price."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, stop_level=1990.0)
        result = mgr.calculate_new_sl(pos, current_price=2001.00)
        # trail = 5 pips = 0.05 → SL = 2001.00 - 0.05 = 2000.95
        assert result == pytest.approx(2000.95, abs=0.01)


class TestTrailingStopSell:
    def _manager(self, activation=10.0, trail=5.0) -> TrailingStopManager:
        return TrailingStopManager(
            activation_pips=activation,
            trail_distance_pips=trail,
            pip_size=0.01,
        )

    def test_no_update_before_activation(self):
        """Trailing should not activate for SELL until price has dropped enough."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(
            direction="SELL", open_level=2000.0,
            current_level=1999.95, stop_level=2010.0
        )
        # Only 5 pips profit — activation requires 10
        result = mgr.calculate_new_sl(pos, current_price=1999.95)
        assert result is None

    def test_sl_moves_down_on_price_drop(self):
        """For SELL, SL should move down as price drops."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="SELL", open_level=2000.0, stop_level=2010.0)

        # 20 pips profit for SELL (price at 1999.80)
        result1 = mgr.calculate_new_sl(pos, current_price=1999.80)
        assert result1 is not None
        assert result1 < 2010.0  # SL moved down

    def test_sl_does_not_move_up_on_price_rise(self):
        """For SELL, SL should NEVER move up."""
        mgr = self._manager(activation=10.0, trail=5.0)
        pos = make_position(direction="SELL", open_level=2000.0, stop_level=2010.0)

        # First: establish trailing
        result1 = mgr.calculate_new_sl(pos, current_price=1999.50)
        assert result1 is not None

        # Price rises back — SL should not move up
        pos2 = make_position(direction="SELL", open_level=2000.0, stop_level=result1)
        result2 = mgr.calculate_new_sl(pos2, current_price=1999.80)
        assert result2 is None  # No update


class TestTrailingStopTracking:
    def test_remove_tracking(self):
        mgr = TrailingStopManager(activation_pips=10.0, trail_distance_pips=5.0)
        pos = make_position(direction="BUY", open_level=2000.0, stop_level=1990.0)

        # Activate trailing
        mgr.calculate_new_sl(pos, current_price=2001.0)
        assert mgr.is_trailing_active("TEST001")

        mgr.remove_tracking("TEST001")
        assert not mgr.is_trailing_active("TEST001")

    def test_not_tracked_initially(self):
        mgr = TrailingStopManager()
        assert not mgr.is_trailing_active("UNKNOWN")

    def test_multiple_positions_independent(self):
        """Two positions should have independent trailing levels."""
        mgr = TrailingStopManager(activation_pips=10.0, trail_distance_pips=5.0)

        pos1 = make_position(deal_id="POS1", direction="BUY", open_level=2000.0, stop_level=1990.0)
        pos2 = make_position(deal_id="POS2", direction="BUY", open_level=2100.0, stop_level=2090.0)

        r1 = mgr.calculate_new_sl(pos1, current_price=2001.0)
        r2 = mgr.calculate_new_sl(pos2, current_price=2101.0)

        # Both should activate independently
        assert r1 is not None
        assert r2 is not None
        assert r1 != r2
