"""Risk Manager integration tests.

Verifies kill switch behavior, drawdown tracking, weekly loss limits,
cooldown logic, and that all 11 pre-trade checks interact correctly.
"""

from datetime import timezone
from unittest.mock import AsyncMock, patch

import pytest

from risk.risk_manager import RiskManager, RiskMetricsCache
from risk.kill_switch import KillSwitch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval_args(**overrides) -> dict:
    """Build default args for RiskManager.approve_trade()."""
    defaults = dict(
        direction="BUY",
        entry_price=2045.0,
        stop_loss=2042.0,
        current_equity=10000.0,
        available_margin=9500.0,
        open_positions=0,
        trades_today=0,
        consecutive_losses=0,
        current_spread=0.5,
        has_open_same_direction=False,
        weekly_loss_pct=0.0,
    )
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Kill Switch Tests
# ---------------------------------------------------------------------------


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_rejects_trade(self):
        """Kill switch active → trade rejected."""
        rm = RiskManager()
        rm.set_initial_equity(10000)
        rm.force_kill_switch("test")

        approval = await rm.approve_trade(**_make_approval_args())
        assert not approval.approved
        assert "kill_switch" in approval.reason

    @pytest.mark.asyncio
    async def test_drawdown_triggers_kill_switch(self):
        """Equity drops below threshold → kill switch auto-activates."""
        rm = RiskManager(kill_switch_drawdown_pct=10.0)
        rm.set_initial_equity(10000)
        rm._equity_peak = 10000

        # Equity dropped to 8900 → 11% drawdown → kill switch
        await rm.approve_trade(**_make_approval_args(current_equity=8900))
        assert rm.kill_switch.is_active

    @pytest.mark.asyncio
    async def test_kill_switch_sync_failure_activates_fail_safe(self):
        """DB sync fails → kill switch activates as fail-safe."""
        ks = KillSwitch(max_drawdown_pct=20.0)
        ks._MAX_DB_SYNC_RETRIES = 1
        assert not ks.is_active

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB down"))

        result = await ks.sync_with_db(mock_session)
        assert result is True  # Fail-safe activated
        assert ks.is_active
        assert "fail-safe" in ks.reason.lower()

    def test_kill_switch_activate_is_idempotent(self):
        """Activating kill switch twice doesn't change reason."""
        ks = KillSwitch()
        ks.activate("first reason")
        assert ks.reason == "first reason"
        ks.activate("second reason")
        assert ks.reason == "first reason"  # Not overwritten

    def test_kill_switch_deactivate(self):
        """Manual deactivation clears state."""
        ks = KillSwitch()
        ks.activate("test")
        assert ks.is_active
        ks.deactivate()
        assert not ks.is_active
        assert ks.reason == ""


# ---------------------------------------------------------------------------
# Pre-Trade Checks
# ---------------------------------------------------------------------------


class TestPreTradeChecks:
    @pytest.mark.asyncio
    async def test_daily_loss_limit_rejects(self):
        """Daily loss exceeds limit → rejected."""
        rm = RiskManager(max_daily_loss_pct=5.0)
        rm.set_initial_equity(10000)

        # Current equity = 9400 → daily loss = 6%
        approval = await rm.approve_trade(**_make_approval_args(current_equity=9400))
        assert not approval.approved
        assert "daily_loss" in approval.reason

    @pytest.mark.asyncio
    async def test_weekly_loss_limit_rejects(self):
        """Weekly loss exceeds limit → rejected."""
        rm = RiskManager(max_weekly_loss_pct=10.0)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(**_make_approval_args(weekly_loss_pct=11.0))
        assert not approval.approved
        assert "weekly_loss" in approval.reason

    @pytest.mark.asyncio
    async def test_max_open_positions_enforced(self):
        """3 positions open → 4th rejected."""
        rm = RiskManager(max_open_positions=3)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(**_make_approval_args(open_positions=3))
        assert not approval.approved
        assert "max_positions" in approval.reason

    @pytest.mark.asyncio
    async def test_same_direction_rejected(self):
        """BUY already open → another BUY rejected."""
        rm = RiskManager()
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(
            **_make_approval_args(has_open_same_direction=True)
        )
        assert not approval.approved
        assert "duplicate" in approval.reason

    @pytest.mark.asyncio
    async def test_spread_too_wide_rejects(self):
        """Spread exceeds max → rejected."""
        rm = RiskManager(max_spread=3.0)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(**_make_approval_args(current_spread=5.0))
        assert not approval.approved
        assert "spread" in approval.reason

    @pytest.mark.asyncio
    async def test_max_trades_per_day_rejects(self):
        """Max daily trades exceeded → rejected."""
        rm = RiskManager(max_trades_per_day=5)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(**_make_approval_args(trades_today=5))
        assert not approval.approved
        assert "max_trades_today" in approval.reason

    @pytest.mark.asyncio
    async def test_cooldown_after_loss_streak(self):
        """Consecutive losses + within cooldown → rejected."""
        rm = RiskManager(max_consecutive_losses=3, cooldown_minutes=30)
        rm.set_initial_equity(10000)
        # Record a recent loss
        rm.record_loss()

        approval = await rm.approve_trade(
            **_make_approval_args(consecutive_losses=3)
        )
        assert not approval.approved
        assert "loss_streak" in approval.reason

    @pytest.mark.asyncio
    async def test_all_checks_pass(self):
        """All parameters within limits → trade approved (mocked time to weekday)."""
        from datetime import datetime as dt

        # Mock datetime.now to return a Wednesday at 10:00 UTC
        mock_now = dt(2026, 3, 4, 10, 0, 0, tzinfo=timezone.utc)  # Wednesday

        rm = RiskManager()
        rm.set_initial_equity(10000)

        with patch("risk.pre_trade_check.datetime") as mock_dt:
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

            # Need to also patch the datetime in risk_manager
            with patch("risk.risk_manager.datetime") as mock_rm_dt:
                mock_rm_dt.now.return_value = mock_now
                mock_rm_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

                approval = await rm.approve_trade(**_make_approval_args())

        assert approval.approved
        assert approval.lot_size > 0
        # PreTradeChecker.run_all now returns 12 results (added: leverage_exceeded)
        assert len(approval.checks) == 12
        assert all(c.passed for c in approval.checks)

    @pytest.mark.asyncio
    async def test_multiple_checks_fail(self):
        """Multiple checks fail → all reported in reason."""
        rm = RiskManager(max_open_positions=1, max_spread=1.0)
        rm.set_initial_equity(10000)

        approval = await rm.approve_trade(
            **_make_approval_args(open_positions=2, current_spread=3.0)
        )
        assert not approval.approved
        assert len(approval.failed_checks) >= 2


# ---------------------------------------------------------------------------
# Risk Metrics Cache
# ---------------------------------------------------------------------------


class TestRiskMetricsCache:
    @pytest.mark.asyncio
    async def test_on_trade_opened_updates_counts(self):
        cache = RiskMetricsCache()
        assert cache.trades_today == 0
        assert cache.open_position_count == 0

        await cache.on_trade_opened()
        assert cache.trades_today == 1
        assert cache.open_position_count == 1

    @pytest.mark.asyncio
    async def test_on_trade_closed_updates_pnl(self):
        cache = RiskMetricsCache()
        cache.open_position_count = 1

        await cache.on_trade_closed(net_pnl=50.0)
        assert cache.daily_pnl == 50.0
        assert cache.weekly_pnl == 50.0
        assert cache.consecutive_losses == 0
        assert cache.open_position_count == 0

    @pytest.mark.asyncio
    async def test_consecutive_losses_tracked(self):
        cache = RiskMetricsCache()
        cache.open_position_count = 3

        await cache.on_trade_closed(net_pnl=-10.0)
        assert cache.consecutive_losses == 1

        await cache.on_trade_closed(net_pnl=-20.0)
        assert cache.consecutive_losses == 2

        # Win resets streak
        await cache.on_trade_closed(net_pnl=5.0)
        assert cache.consecutive_losses == 0

    @pytest.mark.asyncio
    async def test_needs_reconciliation_after_interval(self):
        import time as _t
        cache = RiskMetricsCache()
        assert cache.needs_reconciliation  # Never synced

        cache.last_db_sync = _t.monotonic()
        assert not cache.needs_reconciliation

        # Simulate time passing
        cache.last_db_sync = _t.monotonic() - 600  # 10 min ago
        assert cache.needs_reconciliation

    def test_summary(self):
        cache = RiskMetricsCache()
        cache.trades_today = 5
        cache.daily_pnl = 123.45
        summary = cache.summary()
        assert summary["trades_today"] == 5
        assert summary["daily_pnl"] == 123.45


# ---------------------------------------------------------------------------
# Drawdown Calculation
# ---------------------------------------------------------------------------


class TestDrawdown:
    def test_drawdown_from_peak(self):
        rm = RiskManager()
        rm._equity_peak = 10000.0

        assert rm.get_drawdown_pct(10000) == 0.0
        assert rm.get_drawdown_pct(9500) == pytest.approx(5.0)
        assert rm.get_drawdown_pct(8000) == pytest.approx(20.0)

    def test_daily_loss_pct(self):
        rm = RiskManager()
        rm._equity_start = 10000.0

        assert rm.get_daily_loss_pct(10000) == 0.0
        assert rm.get_daily_loss_pct(10500) == 0.0  # Profit, no loss
        assert rm.get_daily_loss_pct(9700) == pytest.approx(3.0)

    def test_equity_peak_updates_upward_only(self):
        rm = RiskManager()
        rm._equity_peak = 10000
        rm.update_equity_peak(10500)
        assert rm._equity_peak == 10500
        rm.update_equity_peak(10200)
        assert rm._equity_peak == 10500  # Doesn't go down
