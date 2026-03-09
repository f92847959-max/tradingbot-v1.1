"""Tests for async order lock (prevents duplicate orders)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from order_management.order_manager import OrderManager


class TestOrderLock:
    """Test that concurrent open_trade calls are serialized."""

    def test_order_manager_has_lock(self):
        """OrderManager should have an asyncio.Lock."""
        broker = MagicMock()
        manager = OrderManager(broker)
        assert hasattr(manager, "_order_lock")
        assert isinstance(manager._order_lock, asyncio.Lock)

    @pytest.mark.asyncio
    async def test_concurrent_trades_serialized(self):
        """Two concurrent open_trade calls should not run simultaneously."""
        execution_order = []

        broker = MagicMock()
        manager = OrderManager(broker)

        # Mock _execute_trade to track execution order
        original_execute = manager._execute_trade

        async def slow_execute(*args, **kwargs):
            execution_order.append("start")
            await asyncio.sleep(0.1)  # Simulate execution time
            execution_order.append("end")
            return None

        manager._execute_trade = slow_execute

        # Launch two trades concurrently
        await asyncio.gather(
            manager.open_trade("BUY", 0.01, 2040.0, 2050.0),
            manager.open_trade("SELL", 0.01, 2050.0, 2040.0),
        )

        # With lock: should be start-end-start-end (serialized)
        # Without lock: would be start-start-end-end (parallel)
        assert execution_order == ["start", "end", "start", "end"]
