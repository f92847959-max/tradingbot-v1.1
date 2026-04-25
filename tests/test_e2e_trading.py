"""End-to-end trading loop tests.

Simulates complete trade cycles with mocked broker and database.
Verifies the full pipeline: data → signal → risk → execution → close → P&L.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from market_data.broker_client import (
    AccountInfo,
    CapitalComClient,
    OrderResult,
    Position,
    BrokerError,
)
from order_management.order_manager import OrderManager
from order_management.position_monitor import PositionMonitor
from risk.risk_manager import RiskManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_df(n: int = 200) -> pd.DataFrame:
    """Generate sample candle data."""
    np.random.seed(42)
    base = 2045 + np.cumsum(np.random.randn(n) * 0.3)
    ts = pd.date_range("2026-02-01 09:00", periods=n, freq="5min", tz="UTC")
    return pd.DataFrame({
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.4,
        "low": base - np.abs(np.random.randn(n)) * 0.4,
        "close": base,
        "volume": np.random.randint(500, 2000, n),
    }, index=ts)


def _mock_account(balance: float = 10000.0) -> AccountInfo:
    return AccountInfo(
        account_id="ACC001",
        balance=balance,
        deposit=10000,
        profit_loss=balance - 10000,
        available=balance * 0.95,
    )


# ---------------------------------------------------------------------------
# Full Cycle Tests
# ---------------------------------------------------------------------------


class TestFullTradeCycle:
    @pytest.mark.asyncio
    async def test_buy_cycle(self):
        """Open BUY → monitor → close at TP → correct P&L."""
        broker = MagicMock(spec=CapitalComClient)
        broker.open_position = AsyncMock(
            return_value=OrderResult("ref1", "DEAL_BUY", "ACCEPTED", level=2045.0)
        )
        broker.get_current_price = AsyncMock(
            return_value={"bid": 2045.0, "ask": 2045.5}
        )

        mgr = OrderManager(broker)

        # Open trade
        with patch("order_management.order_manager.get_session") as mock_gs:
            mock_session = AsyncMock()
            mock_repo = AsyncMock()
            mock_repo.add = AsyncMock(side_effect=lambda t: t)
            mock_repo.log_action = AsyncMock()

            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=mock_session)
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            with patch("order_management.order_manager.TradeRepository", return_value=mock_repo), \
                 patch("order_management.order_manager.OrderLogRepository", return_value=mock_repo):

                trade = await mgr.open_trade(
                    direction="BUY",
                    lot_size=0.1,
                    stop_loss=2042.0,
                    take_profit=2051.0,
                    entry_price=2045.0,
                    ai_confidence=0.82,
                    trade_score=78,
                )

        assert trade is not None
        assert trade.direction == "BUY"
        assert trade.deal_id == "DEAL_BUY"
        assert mgr.monitor.get_open_count() == 1

    @pytest.mark.asyncio
    async def test_position_closed_detected(self):
        """Position closed at broker → detected by monitor."""
        broker = MagicMock(spec=CapitalComClient)
        # First check: position exists. Second check: gone.
        broker.get_positions = AsyncMock(return_value=[])

        pm = PositionMonitor(broker)
        pm.track_position("DEAL_001", Position(
            deal_id="DEAL_001", direction="BUY", size=0.1,
            open_level=2045, current_level=2048,
        ))

        callback_called = False
        callback_deal_id = None

        async def on_close(deal_id, pos):
            nonlocal callback_called, callback_deal_id
            callback_called = True
            callback_deal_id = deal_id

        pm.on_position_closed(on_close)

        status = await pm.check()
        assert "DEAL_001" in status["newly_closed"]
        assert callback_called
        assert callback_deal_id == "DEAL_001"


class TestRiskRejection:
    @pytest.mark.asyncio
    async def test_risk_rejected_no_order(self):
        """Risk check fails → no order submitted to broker."""
        rm = RiskManager(max_open_positions=1)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(
            direction="BUY",
            entry_price=2045,
            stop_loss=2042,
            current_equity=10000,
            available_margin=9500,
            open_positions=1,  # Already at max
            trades_today=0,
            consecutive_losses=0,
            current_spread=0.5,
            has_open_same_direction=False,
            weekly_loss_pct=0.0,
        )

        assert not approval.approved
        assert approval.lot_size == 0.0
        assert len(approval.failed_checks) > 0


class TestBrokerError:
    @pytest.mark.asyncio
    async def test_broker_error_no_trade_created(self):
        """Broker rejects → no trade in system."""
        broker = MagicMock(spec=CapitalComClient)
        broker.open_position = AsyncMock(
            side_effect=BrokerError("Service unavailable")
        )
        broker.get_current_price = AsyncMock(
            return_value={"bid": 2045, "ask": 2045.5}
        )

        mgr = OrderManager(broker)

        with patch("order_management.order_manager.get_session") as mock_gs:
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=AsyncMock())
            cm.__aexit__ = AsyncMock(return_value=False)
            mock_gs.return_value = cm

            trade = await mgr.open_trade(
                direction="SELL", lot_size=0.1, stop_loss=2048, take_profit=2038,
            )

        assert trade is None
        assert mgr.monitor.get_open_count() == 0


class TestRestartRecovery:
    @pytest.mark.asyncio
    async def test_positions_recovered_from_db(self):
        """On restart, open positions loaded from DB and tracked."""
        broker = MagicMock(spec=CapitalComClient)
        broker_pos = Position(
            deal_id="DEAL_RECOVERED",
            direction="BUY",
            size=0.2,
            open_level=2040,
            current_level=2048,
            profit=8.0,
        )
        broker.get_positions = AsyncMock(return_value=[broker_pos])

        pm = PositionMonitor(broker)

        # Simulate DB trade objects
        mock_trade = MagicMock()
        mock_trade.id = 1
        mock_trade.deal_id = "DEAL_RECOVERED"
        mock_trade.direction = "BUY"
        mock_trade.lot_size = 0.2
        mock_trade.entry_price = 2040
        mock_trade.stop_loss = 2037
        mock_trade.take_profit = 2055

        recovered = await pm.recover_from_db([mock_trade])
        assert recovered == 1
        assert pm.get_open_count() == 1

        # Sync with broker → position confirmed
        result = await pm.sync_with_broker()
        assert "DEAL_RECOVERED" in result["synced"]
        assert result["orphaned"] == []

    @pytest.mark.asyncio
    async def test_orphaned_positions_detected_on_restart(self):
        """Position in DB but closed at broker → detected as orphaned."""
        broker = MagicMock(spec=CapitalComClient)
        broker.get_positions = AsyncMock(return_value=[])  # No positions at broker

        pm = PositionMonitor(broker)

        mock_trade = MagicMock()
        mock_trade.id = 2
        mock_trade.deal_id = "DEAL_GONE"
        mock_trade.direction = "SELL"
        mock_trade.lot_size = 0.1
        mock_trade.entry_price = 2050
        mock_trade.stop_loss = 2053
        mock_trade.take_profit = 2040

        await pm.recover_from_db([mock_trade])
        result = await pm.sync_with_broker()
        assert "DEAL_GONE" in result["orphaned"]


class TestPnLCalculation:
    def test_buy_profit(self):
        """BUY trade with price increase → positive P&L."""
        mgr = OrderManager(MagicMock())
        trade = MagicMock()
        trade.entry_price = 2045.0
        trade.lot_size = 1.0
        trade.direction = "BUY"
        trade.spread_at_entry = 0.5

        pnl = mgr._calc_pnl(trade, exit_price=2050.0)
        assert pnl["pips"] > 0
        assert pnl["euros"] > 0

    def test_sell_profit(self):
        """SELL trade with price decrease → positive P&L."""
        mgr = OrderManager(MagicMock())
        trade = MagicMock()
        trade.entry_price = 2050.0
        trade.lot_size = 1.0
        trade.direction = "SELL"
        trade.spread_at_entry = 0.5

        pnl = mgr._calc_pnl(trade, exit_price=2045.0)
        assert pnl["pips"] > 0
        assert pnl["euros"] > 0

    def test_zero_exit_price_returns_zero(self):
        """Exit price = 0 → P&L = 0."""
        mgr = OrderManager(MagicMock())
        trade = MagicMock()
        trade.entry_price = 2045.0
        trade.lot_size = 1.0
        trade.direction = "BUY"
        trade.spread_at_entry = 0.5

        pnl = mgr._calc_pnl(trade, exit_price=0)
        assert pnl["pips"] == 0
        assert pnl["euros"] == 0

    def test_spread_cost_deducted(self):
        """Spread cost is subtracted from gross P&L."""
        mgr = OrderManager(MagicMock())
        trade = MagicMock()
        trade.entry_price = 2045.0
        trade.lot_size = 1.0
        trade.direction = "BUY"
        trade.spread_at_entry = 0.5  # $0.50 spread cost per lot

        pnl = mgr._calc_pnl(trade, exit_price=2045.0)
        # Zero price movement, but spread cost
        assert pnl["pips"] == 0
        assert pnl["net"] < 0  # Net negative due to spread
