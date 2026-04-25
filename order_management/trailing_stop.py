"""Trailing stop — dynamically adjusts stop loss as price moves in favor."""

import logging

from market_data.broker_client import Position

logger = logging.getLogger(__name__)


class TrailingStopManager:
    """Manages trailing stops for open positions.

    Activation: Trailing stop activates when profit exceeds activation_pips.
    Trail distance: SL follows price at trail_distance_pips behind.
    """

    def __init__(
        self,
        activation_pips: float = 10.0,
        trail_distance_pips: float = 5.0,
        pip_size: float = 0.01,
    ) -> None:
        self.activation_pips = activation_pips
        self.trail_distance_pips = trail_distance_pips
        self.pip_size = pip_size
        # deal_id -> current trailing SL level
        self._trailing_levels: dict[str, float] = {}

    def calculate_new_sl(
        self, position: Position, current_price: float
    ) -> float | None:
        """Calculate new SL if trailing should move.

        Returns new SL price if it should be updated, None otherwise.
        """
        deal_id = position.deal_id
        direction = position.direction
        open_level = position.open_level
        current_sl = position.stop_level

        # Calculate profit in pips
        if direction == "BUY":
            profit_pips = (current_price - open_level) / self.pip_size
        else:
            profit_pips = (open_level - current_price) / self.pip_size

        # Not enough profit to activate trailing
        if profit_pips < self.activation_pips:
            return None

        # Calculate ideal trailing SL
        trail_distance = self.trail_distance_pips * self.pip_size
        if direction == "BUY":
            new_sl = current_price - trail_distance
            # FIXME: spread consideration — when a live spread feed is wired
            # in, subtract spread/2 here for BUY (and add for SELL) so the
            # trailing stop accounts for the bid/ask gap and isn't tripped by
            # normal spread fluctuation. Currently no spread access at this
            # call site (Position carries no spread field).
        else:
            new_sl = current_price + trail_distance
            # FIXME: spread consideration — see BUY branch above.

        # Round BEFORE the monotonicity check so that the value we compare
        # against current_sl / previous_trailing is the same value we'll
        # ultimately persist. Otherwise rounding after the check can violate
        # the monotonicity invariant (e.g. an unrounded 1234.567 passes the
        # ">previous" guard, gets rounded down to 1234.57, and ends up equal
        # or worse than the previous level we just stored).
        new_sl = round(new_sl, 2)

        # Only move SL in favorable direction
        previous_trailing = self._trailing_levels.get(deal_id)

        if direction == "BUY":
            # SL should only move up
            if current_sl and new_sl <= current_sl:
                return None
            if previous_trailing and new_sl <= previous_trailing:
                return None
        else:
            # SL should only move down
            if current_sl and new_sl >= current_sl:
                return None
            if previous_trailing and new_sl >= previous_trailing:
                return None

        # Update tracking with the same rounded value we are about to return.
        self._trailing_levels[deal_id] = new_sl

        logger.info(
            "Trailing SL update: deal=%s, direction=%s, profit=%.1f pips, new_sl=%.2f (was %s)",
            deal_id, direction, profit_pips, new_sl,
            f"{current_sl:.2f}" if current_sl else "none",
        )
        return new_sl

    def remove_tracking(self, deal_id: str) -> None:
        """Remove trailing tracking for a closed position."""
        self._trailing_levels.pop(deal_id, None)

    def is_trailing_active(self, deal_id: str) -> bool:
        return deal_id in self._trailing_levels
