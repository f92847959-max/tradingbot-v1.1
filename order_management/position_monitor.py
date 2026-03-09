"""Position monitor — track open positions and detect closes.

Persists known positions: on startup, loads open trades from DB and syncs
with the broker to recover state after restarts.
"""

import logging
from datetime import datetime, timezone
from typing import Callable, Any, Sequence

from market_data.broker_client import CapitalComClient, Position

logger = logging.getLogger(__name__)


class PositionMonitor:
    """Monitors open positions and detects when they are closed (TP/SL hit).

    Positions are tracked both in-memory (for fast lookups) and persisted to DB
    (for recovery after restart). The broker is the single source of truth.
    """

    def __init__(self, broker_client: CapitalComClient) -> None:
        self.client = broker_client
        self._known_positions: dict[str, Position] = {}
        self._on_close_callbacks: list[Callable] = []

    def on_position_closed(self, callback: Callable[[str, Position], Any]) -> None:
        """Register a callback for when a position is closed."""
        self._on_close_callbacks.append(callback)

    async def recover_from_db(self, open_trades: Sequence[Any]) -> int:
        """Load open trades from database into tracking on startup.

        Args:
            open_trades: Sequence of Trade ORM objects with status=OPEN

        Returns:
            Number of positions recovered.
        """
        recovered = 0
        for trade in open_trades:
            if not trade.deal_id:
                logger.warning(
                    "Open trade id=%d has no deal_id — cannot track", trade.id
                )
                continue
            # Create a Position object from DB trade data
            pos = Position(
                deal_id=trade.deal_id,
                direction=trade.direction,
                size=float(trade.lot_size),
                open_level=float(trade.entry_price),
                current_level=float(trade.entry_price),  # will be updated on next check
                stop_level=float(trade.stop_loss) if trade.stop_loss else None,
                limit_level=float(trade.take_profit) if trade.take_profit else None,
                profit=0.0,
            )
            self._known_positions[trade.deal_id] = pos
            recovered += 1

        if recovered:
            logger.info("Recovered %d open positions from database", recovered)
        return recovered

    async def sync_with_broker(self) -> dict:
        """Full sync: compare DB-tracked positions with broker state.

        Returns dict with:
        - orphaned: deal_ids in DB but not at broker (positions closed externally)
        - untracked: deal_ids at broker but not in DB (opened outside this system)
        - synced: deal_ids present in both
        """
        try:
            broker_positions = await self.client.get_positions()
        except Exception as e:
            logger.error("Failed to sync with broker: %s", e)
            return {"orphaned": [], "untracked": [], "synced": [], "error": str(e)}

        broker_ids = {p.deal_id: p for p in broker_positions}
        known_ids = set(self._known_positions.keys())
        broker_id_set = set(broker_ids.keys())

        orphaned = list(known_ids - broker_id_set)
        untracked = list(broker_id_set - known_ids)
        synced = list(known_ids & broker_id_set)

        # Update current levels for synced positions
        for deal_id in synced:
            self._known_positions[deal_id] = broker_ids[deal_id]

        if orphaned:
            logger.warning(
                "Found %d orphaned positions (in DB but not at broker): %s",
                len(orphaned), orphaned,
            )
        if untracked:
            logger.warning(
                "Found %d untracked positions (at broker but not in DB): %s",
                len(untracked), untracked,
            )

        return {"orphaned": orphaned, "untracked": untracked, "synced": synced}

    async def check(self) -> dict:
        """Check current positions against known state.

        Uses the broker as single source of truth. Positions in _known_positions
        that are no longer at the broker are considered closed.

        Returns dict with:
        - still_open: list of deal_ids still open
        - newly_closed: list of deal_ids that were closed since last check
        - new_positions: list of deal_ids that appeared (shouldn't happen in normal flow)
        """
        try:
            current = await self.client.get_positions()
        except Exception as e:
            logger.error("Failed to fetch positions: %s", e)
            return {
                "still_open": list(self._known_positions.keys()),
                "newly_closed": [],
                "new_positions": [],
                "error": str(e),
            }

        current_ids = {p.deal_id: p for p in current}
        known_ids = set(self._known_positions.keys())
        current_id_set = set(current_ids.keys())

        still_open = list(known_ids & current_id_set)
        newly_closed = list(known_ids - current_id_set)
        new_positions = list(current_id_set - known_ids)

        # Fire callbacks for closed positions
        for deal_id in newly_closed:
            old_pos = self._known_positions[deal_id]
            logger.info(
                "Position closed: deal_id=%s, direction=%s, open=%.2f, profit=%.2f",
                deal_id, old_pos.direction, old_pos.open_level, old_pos.profit,
            )
            for cb in self._on_close_callbacks:
                try:
                    await cb(deal_id, old_pos)
                except Exception as e:
                    logger.error("Error in close callback for %s: %s", deal_id, e)

        # Update known state — broker is the source of truth
        self._known_positions = current_ids

        if newly_closed or new_positions:
            logger.info(
                "Position check: %d open, %d closed, %d new",
                len(still_open), len(newly_closed), len(new_positions),
            )

        return {
            "still_open": still_open,
            "newly_closed": newly_closed,
            "new_positions": new_positions,
        }

    def track_position(self, deal_id: str, position: Position) -> None:
        """Add a position to tracking (called after opening a trade)."""
        self._known_positions[deal_id] = position
        logger.debug("Now tracking position: deal_id=%s", deal_id)

    def untrack_position(self, deal_id: str) -> None:
        """Remove a position from tracking."""
        self._known_positions.pop(deal_id, None)

    def get_open_count(self) -> int:
        return len(self._known_positions)

    def get_open_positions(self) -> dict[str, Position]:
        return dict(self._known_positions)

    def has_position_in_direction(self, direction: str) -> bool:
        return any(p.direction == direction for p in self._known_positions.values())
