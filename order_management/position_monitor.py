"""Position monitor — track open positions and detect closes.

Persists known positions: on startup, loads open trades from DB and syncs
with the broker to recover state after restarts.
"""

import logging
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
        self._on_partial_fill_callbacks: list[Callable] = []
        self._runtime_context: dict[str, dict[str, Any]] = {}
        # Deal IDs whose close-callbacks failed and must be retried on next check.
        self._close_retry: dict[str, Position] = {}
        # Set when a broker fetch fails — forces a reconciliation on next
        # successful fetch before computing newly_closed (which would otherwise
        # produce false positives across a transient disconnect).
        self._last_sync_failed: bool = False

    def on_position_closed(self, callback: Callable[[str, Position], Any]) -> None:
        """Register a callback for when a position is closed."""
        self._on_close_callbacks.append(callback)

    def on_partial_fill(self, callback: Callable[[str, Position, Position], Any]) -> None:
        """Register a callback for when a position's size changes (partial fill)."""
        self._on_partial_fill_callbacks.append(callback)

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
            # Mark sync as failed so that the next successful check performs a
            # reconciliation pass before computing newly_closed. Without this,
            # a transient broker disconnect followed by a recovery could mark
            # every known position as "newly closed" simply because the
            # interim fetch returned an empty (or partial) list.
            self._last_sync_failed = True
            logger.error("Failed to fetch positions: %s", e)
            return {
                "still_open": list(self._known_positions.keys()),
                "newly_closed": [],
                "new_positions": [],
                "error": str(e),
            }

        current_ids = {p.deal_id: p for p in current}

        # Reconciliation after a broker-disconnect: if the previous fetch
        # failed, do not interpret missing deal_ids as closes — instead drop
        # any in-memory entries that the broker is now silent on, but treat
        # them as state-drift (logged) rather than firing on_close callbacks.
        if self._last_sync_failed:
            current_id_set = set(current_ids.keys())
            drift = [
                d for d in list(self._known_positions.keys())
                if d not in current_id_set
            ]
            if drift:
                logger.warning(
                    "Reconciliation after broker reconnect: dropping %d "
                    "in-memory positions absent from broker without firing "
                    "close callbacks (state-drift): %s",
                    len(drift), drift,
                )
                for d in drift:
                    self._known_positions.pop(d, None)
            self._last_sync_failed = False

        known_ids = set(self._known_positions.keys())
        current_id_set = set(current_ids.keys())

        still_open = list(known_ids & current_id_set)
        newly_closed = list(known_ids - current_id_set)
        new_positions = list(current_id_set - known_ids)

        # Re-include any deal_ids whose close-callback previously failed and
        # which are *still* absent from the broker — they need another
        # callback attempt before we forget about them.
        for retry_id in list(self._close_retry.keys()):
            if retry_id not in current_id_set and retry_id not in newly_closed:
                newly_closed.append(retry_id)

        # Partial-fill detection: positions present on both sides but with
        # changed size. Fire on_partial_fill callbacks (or at least WARN).
        for deal_id in still_open:
            old_pos = self._known_positions[deal_id]
            new_pos = current_ids[deal_id]
            try:
                old_size = float(old_pos.size)
                new_size = float(new_pos.size)
            except (TypeError, ValueError):
                continue
            if abs(old_size - new_size) > 1e-9:
                logger.warning(
                    "Partial fill / size change detected: deal=%s old_size=%.4f new_size=%.4f",
                    deal_id, old_size, new_size,
                )
                if self._on_partial_fill_callbacks:
                    for cb in self._on_partial_fill_callbacks:
                        try:
                            await cb(deal_id, old_pos, new_pos)
                        except Exception as cb_err:
                            logger.error(
                                "Error in partial-fill callback for %s: %s",
                                deal_id, cb_err,
                            )

        # Update still-open positions to broker state up front (broker is
        # source of truth for stop/limit/profit/current_level on live deals).
        for deal_id in still_open:
            self._known_positions[deal_id] = current_ids[deal_id]
        # Add brand-new (untracked) positions to the in-memory map.
        for deal_id in new_positions:
            self._known_positions[deal_id] = current_ids[deal_id]

        # Fire callbacks for closed positions ONE AT A TIME and only forget
        # the deal_id once every callback succeeded. If any callback raises,
        # the position is kept in a retry map and will be attempted again on
        # the next check.
        for deal_id in newly_closed:
            old_pos = (
                self._known_positions.get(deal_id)
                or self._close_retry.get(deal_id)
            )
            if old_pos is None:
                continue
            logger.info(
                "Position closed: deal_id=%s, direction=%s, open=%.2f, profit=%.2f",
                deal_id, old_pos.direction, old_pos.open_level, old_pos.profit,
            )
            cb_failure = False
            for cb in self._on_close_callbacks:
                try:
                    await cb(deal_id, old_pos)
                except Exception as e:
                    cb_failure = True
                    logger.error(
                        "Error in close callback for %s: %s — will retry on next check",
                        deal_id, e,
                    )
            if cb_failure:
                # Keep position so we can retry; do NOT pop from _known_positions
                # if it was still there.
                self._close_retry[deal_id] = old_pos
                if deal_id not in self._known_positions:
                    self._known_positions[deal_id] = old_pos
            else:
                self._known_positions.pop(deal_id, None)
                self._close_retry.pop(deal_id, None)

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
        self._runtime_context.pop(deal_id, None)

    def get_open_count(self) -> int:
        return len(self._known_positions)

    def get_open_positions(self) -> dict[str, Position]:
        return dict(self._known_positions)

    def has_position_in_direction(self, direction: str) -> bool:
        return any(p.direction == direction for p in self._known_positions.values())

    def set_runtime_context(self, deal_id: str, context: dict[str, Any]) -> None:
        self._runtime_context[deal_id] = dict(context)

    def get_runtime_context(self, deal_id: str) -> dict[str, Any]:
        return dict(self._runtime_context.get(deal_id, {}))
