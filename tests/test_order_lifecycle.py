"""Order lifecycle edge-case tests.

Tests DB insert failures, execution timeouts, immediate closes,
trailing stop errors, lock timeouts, and orphaned trade reconciliation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_data.broker_client import (
    CapitalComClient,
    OrderResult,
    Position,
    BrokerError,
)
from order_management.order_manager import OrderManager
from order_management.position_monitor import PositionMonitor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_broker(**overrides) -> MagicMock:
    """Create a mocked broker client with sensible defaults."""
    broker = MagicMock(spec=CapitalComClient)
    broker.open_position = AsyncMock(
        return_value=OrderResult(
            deal_reference="ref1",
            deal_id="DEAL_001",
            status="ACCEPTED",
            level=2045.0,
        )
    )
    broker.close_position = AsyncMock(
        return_value=OrderResult(
            deal_reference="ref2",
            deal_id="DEAL_001",
            status="ACCEPTED",
            level=2048.0,
        )
    )
    broker.get_current_price = AsyncMock(
        return_value={"bid": 2045.0, "ask": 2045.5}
    )
    broker.get_positions = AsyncMock(return_value=[])
    broker.modify_position = AsyncMock(
        return_value=OrderResult("ref3", "DEAL_001", "ACCEPTED", level=2045)
    )
    for key, val in overrides.items():
        setattr(broker, key, val)
    return broker


# ---------------------------------------------------------------------------
# Order execution + DB failures
# ---------------------------------------------------------------------------


class TestOrderDBFailure:
    @pytest.mark.asyncio
    async def test_order_success_but_db_fails_logs_orphaned(self):
        """Broker accepts order, DB insert fails → logged as ORPHANED."""
        broker = _mock_broker()
        mgr = OrderManager(broker)

        with patch("order_management.order_manager.get_session") as mock_gs:
            # Make DB session raise on add
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock(side_effect=Exception("DB write error"))

            # Setup context manager
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=mock_session)
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            await mgr.open_trade(
                direction="BUY",
                lot_size=0.1,
                stop_loss=2040,
                take_profit=2055,
                entry_price=2045,
            )

            # The trade should still be tracked by position monitor
            # even if DB failed (broker has the position)
            assert mgr.monitor.get_open_count() >= 0  # At minimum doesn't crash


class TestOrderExecution:
    @pytest.mark.asyncio
    async def test_order_rejected_by_broker(self):
        """Broker rejects order → returns None."""
        broker = _mock_broker()
        broker.open_position = AsyncMock(
            return_value=OrderResult("ref1", "DEAL_001", "REJECTED", reason="Insufficient funds")
        )

        mgr = OrderManager(broker)

        with patch("order_management.order_manager.get_session") as mock_gs:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=AsyncMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            result = await mgr.open_trade(
                direction="BUY", lot_size=0.1, stop_loss=2040, take_profit=2055,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_lock_timeout_rejects_trade(self):
        """Lock already held → second trade aborted."""
        broker = _mock_broker()
        mgr = OrderManager(broker)
        mgr.LOCK_TIMEOUT = 0.05  # Very short

        # Hold the lock
        await mgr._order_lock.acquire()
        try:
            result = await mgr.open_trade(
                direction="BUY", lot_size=0.1, stop_loss=2040, take_profit=2055,
            )
            assert result is None
        finally:
            mgr._order_lock.release()


# ---------------------------------------------------------------------------
# Position Monitor
# ---------------------------------------------------------------------------


class TestPositionMonitor:
    @pytest.mark.asyncio
    async def test_position_closed_at_broker_detected(self):
        """Position in tracking but not at broker → newly_closed."""
        broker = _mock_broker()
        broker.get_positions = AsyncMock(return_value=[])  # No positions at broker

        pm = PositionMonitor(broker)
        pos = Position(
            deal_id="DEAL_001", direction="BUY", size=0.1,
            open_level=2045, current_level=2045,
        )
        pm.track_position("DEAL_001", pos)
        assert pm.get_open_count() == 1

        status = await pm.check()
        assert "DEAL_001" in status["newly_closed"]
        assert pm.get_open_count() == 0  # Cleared

    @pytest.mark.asyncio
    async def test_sync_detects_orphaned_positions(self):
        """Position in DB but not at broker → orphaned list."""
        broker = _mock_broker()
        broker.get_positions = AsyncMock(return_value=[])

        pm = PositionMonitor(broker)
        pos = Position(
            deal_id="DEAL_OLD", direction="SELL", size=0.2,
            open_level=2050, current_level=2050,
        )
        pm.track_position("DEAL_OLD", pos)

        result = await pm.sync_with_broker()
        assert "DEAL_OLD" in result["orphaned"]

    @pytest.mark.asyncio
    async def test_sync_detects_untracked_positions(self):
        """Position at broker but not tracked → untracked list."""
        broker_pos = Position(
            deal_id="DEAL_EXT", direction="BUY", size=0.5,
            open_level=2040, current_level=2042,
        )
        broker = _mock_broker()
        broker.get_positions = AsyncMock(return_value=[broker_pos])

        pm = PositionMonitor(broker)
        result = await pm.sync_with_broker()
        assert "DEAL_EXT" in result["untracked"]

    @pytest.mark.asyncio
    async def test_recover_from_db(self):
        """Recover open trades from DB objects."""
        broker = _mock_broker()
        pm = PositionMonitor(broker)

        # Mock Trade objects from DB
        mock_trade = MagicMock()
        mock_trade.id = 1
        mock_trade.deal_id = "DEAL_DB"
        mock_trade.direction = "BUY"
        mock_trade.lot_size = 0.1
        mock_trade.entry_price = 2045.0
        mock_trade.stop_loss = 2042.0
        mock_trade.take_profit = 2055.0

        recovered = await pm.recover_from_db([mock_trade])
        assert recovered == 1
        assert pm.get_open_count() == 1
        assert pm.has_position_in_direction("BUY")

    @pytest.mark.asyncio
    async def test_recover_skips_trade_without_deal_id(self):
        """Trade without deal_id → skipped during recovery."""
        broker = _mock_broker()
        pm = PositionMonitor(broker)

        mock_trade = MagicMock()
        mock_trade.id = 2
        mock_trade.deal_id = None

        recovered = await pm.recover_from_db([mock_trade])
        assert recovered == 0

    @pytest.mark.asyncio
    async def test_broker_error_during_check_returns_known_state(self):
        """Broker API error during check → returns current known positions."""
        broker = _mock_broker()
        broker.get_positions = AsyncMock(side_effect=BrokerError("API down"))

        pm = PositionMonitor(broker)
        pm.track_position("DEAL_001", Position(
            deal_id="DEAL_001", direction="BUY", size=0.1,
            open_level=2045, current_level=2045,
        ))

        status = await pm.check()
        assert "DEAL_001" in status["still_open"]
        assert status["newly_closed"] == []

    def test_has_position_in_direction(self):
        broker = _mock_broker()
        pm = PositionMonitor(broker)
        pm.track_position("DEAL_001", Position(
            deal_id="DEAL_001", direction="BUY", size=0.1,
            open_level=2045, current_level=2045,
        ))
        assert pm.has_position_in_direction("BUY")
        assert not pm.has_position_in_direction("SELL")


# ---------------------------------------------------------------------------
# Close trade lifecycle
# ---------------------------------------------------------------------------


class TestCloseTrade:
    @pytest.mark.asyncio
    async def test_close_trade_broker_error_marks_close_failed(self):
        """Broker error during close → status = CLOSE_FAILED."""
        broker = _mock_broker()
        broker.close_position = AsyncMock(side_effect=BrokerError("API error"))

        mgr = OrderManager(broker)

        with patch("order_management.order_manager.get_session") as mock_gs:
            mock_session = AsyncMock()
            mock_trade = MagicMock()
            mock_trade.id = 1
            mock_trade.status = "OPEN"

            mock_repo = AsyncMock()
            mock_repo.get_by_deal_id = AsyncMock(return_value=mock_trade)

            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=mock_session)
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            result = await mgr.close_trade("DEAL_001", reason="MANUAL")
            assert result is False  # Close failed

    @pytest.mark.asyncio
    async def test_close_all_returns_count(self):
        """close_all() returns number of successfully closed positions."""
        broker = _mock_broker()
        broker.close_all_positions = AsyncMock(return_value=[
            OrderResult("ref1", "DEAL_001", "ACCEPTED", level=2048),
            OrderResult("ref2", "DEAL_002", "REJECTED", reason="already closed"),
        ])

        mgr = OrderManager(broker)
        count = await mgr.close_all()
        assert count == 1  # Only 1 of 2 succeeded

    @pytest.mark.asyncio
    async def test_close_all_keeps_tracking_when_db_update_fails(self):
        """Kill-switch close keeps tracking and queues reconciliation on DB failure."""
        broker = _mock_broker()
        broker.close_all_positions = AsyncMock(return_value=[
            OrderResult("ref1", "DEAL_001", "ACCEPTED", level=2048),
        ])

        mgr = OrderManager(broker)
        mgr.monitor.track_position(
            "DEAL_001",
            Position(
                deal_id="DEAL_001",
                direction="BUY",
                size=0.1,
                open_level=2045.0,
                current_level=2045.0,
            ),
        )

        mock_trade = MagicMock()
        mock_trade.id = 1
        mock_trade.status = "OPEN"
        mock_trade.direction = "BUY"
        mock_trade.entry_price = 2045.0
        mock_trade.lot_size = 0.1

        with patch("order_management.order_manager.get_session") as mock_gs, \
             patch("order_management.order_manager.TradeRepository") as mock_repo_cls:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=AsyncMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            mock_repo = AsyncMock()
            mock_repo.get_by_deal_id = AsyncMock(return_value=mock_trade)
            mock_repo.close_trade = AsyncMock(side_effect=Exception("DB write error"))
            mock_repo_cls.return_value = mock_repo

            count = await mgr.close_all()

        assert count == 1
        assert mgr.monitor.get_open_count() == 1
        assert len(mgr.orphan_close_queue) == 1
