"""Integration tests for advanced risk components wired into RiskManager -- Phase 9 Plan 03."""

import asyncio
import pytest

from risk.risk_manager import RiskManager
from risk.portfolio_heat import PortfolioHeatManager
from risk.equity_curve_filter import EquityCurveFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_rm(**kwargs) -> RiskManager:
    """Create a RiskManager with safe defaults for tests."""
    defaults = dict(
        max_risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
        max_open_positions=3,
        max_portfolio_heat_pct=5.0,
        equity_curve_ema_period=20,
        equity_curve_filter_enabled=True,
    )
    defaults.update(kwargs)
    return RiskManager(**defaults)


def run_approve(rm, *, confidence=0.7, atr=3.0, equity=10000.0,
                entry_price=2050.0, stop_loss=2045.0):
    """Helper: synchronously call approve_trade using asyncio.run."""
    rm.set_initial_equity(equity)

    async def _do():
        return await rm.approve_trade(
            direction="BUY",
            entry_price=entry_price,
            stop_loss=stop_loss,
            current_equity=equity,
            available_margin=5000.0,
            open_positions=0,
            trades_today=5,
            consecutive_losses=0,
            current_spread=0.5,
            has_open_same_direction=False,
            confidence=confidence,
            atr=atr,
        )

    return asyncio.run(_do())


# ---------------------------------------------------------------------------
# Tests: initialization and new methods
# ---------------------------------------------------------------------------

class TestRiskManagerAdvancedInit:
    def test_has_advanced_sizer(self):
        rm = make_rm()
        assert rm.advanced_sizer is not None

    def test_has_portfolio_heat(self):
        rm = make_rm()
        assert isinstance(rm.portfolio_heat, PortfolioHeatManager)

    def test_has_equity_filter(self):
        rm = make_rm()
        assert isinstance(rm.equity_filter, EquityCurveFilter)

    def test_get_portfolio_heat_zero_when_no_positions(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        assert rm.get_portfolio_heat() == pytest.approx(0.0)

    def test_status_includes_advanced_keys(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        s = rm.status()
        assert "portfolio_heat" in s
        assert "equity_curve_filter" in s
        assert "kelly_fraction" in s


class TestUpdateTradeStats:
    def test_update_trade_stats_changes_kelly_fraction(self):
        rm = make_rm()
        rm.update_trade_stats(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
        assert rm.advanced_sizer._kelly_fraction > 0.0

    def test_update_trade_stats_affects_kelly_fraction_in_status(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.update_trade_stats(win_rate=0.7, avg_win=3.0, avg_loss=1.0)
        assert rm.advanced_sizer._kelly_fraction > 0.0
        assert rm.status()["kelly_fraction"] == rm.advanced_sizer._kelly_fraction


class TestOnPositionOpenedClosed:
    def test_on_position_opened_updates_heat(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.on_position_opened(risk_amount=200, account_balance=10000.0)
        assert rm.get_portfolio_heat() == pytest.approx(2.0)

    def test_on_position_closed_reduces_heat(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.on_position_opened(risk_amount=200, account_balance=10000.0)
        rm.on_position_closed(risk_amount=200, account_balance=10000.0, equity=10000.0)
        assert rm.get_portfolio_heat() == pytest.approx(0.0)

    def test_on_position_closed_updates_equity_filter(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.on_position_opened(risk_amount=100, account_balance=10000.0)
        rm.on_position_closed(risk_amount=100, account_balance=10000.0, equity=10200.0)
        # With only 1 data point, filter should report insufficient data
        assert rm.equity_filter.get_equity_vs_ema() == "insufficient_data"


# ---------------------------------------------------------------------------
# Tests: is_trading_allowed
# ---------------------------------------------------------------------------

class TestIsTradingAllowed:
    def test_allowed_by_default(self):
        rm = make_rm()
        assert rm.is_trading_allowed() is True

    def test_blocked_when_kill_switch_active(self):
        rm = make_rm()
        rm.kill_switch.activate("test")
        assert rm.is_trading_allowed() is False

    def test_blocked_by_equity_filter(self):
        rm = make_rm(equity_curve_ema_period=5)
        # Seed EMA high
        for _ in range(5):
            rm.equity_filter.update(11000.0)
        # Drop below EMA
        for _ in range(3):
            rm.equity_filter.update(9000.0)
        assert rm.is_trading_allowed() is False


# ---------------------------------------------------------------------------
# Tests: approve_trade with advanced checks
# ---------------------------------------------------------------------------

class TestApproveTradeAdvanced:
    def test_backward_compat_no_confidence_atr_params(self):
        """approve_trade still works without confidence/atr (uses defaults)."""
        rm = make_rm()
        rm.set_initial_equity(10000.0)

        async def _do():
            return await rm.approve_trade(
                direction="BUY",
                entry_price=2050.0,
                stop_loss=2045.0,
                current_equity=10000.0,
                available_margin=5000.0,
                open_positions=0,
                trades_today=5,
                consecutive_losses=0,
                current_spread=0.5,
                has_open_same_direction=False,
                # NOTE: confidence and atr not passed (using defaults)
            )

        result = asyncio.run(_do())
        assert result.approved is True

    def test_uses_advanced_sizer_when_kelly_data_available(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.update_trade_stats(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
        result = run_approve(rm, confidence=0.8, atr=3.0)
        # Should be approved with advanced sizing
        assert result.approved is True
        assert "Sizing" in result.reason or "sizing" in result.reason.lower()

    def test_rejected_when_portfolio_heat_exceeded(self):
        rm = make_rm(max_portfolio_heat_pct=4.0)
        rm.set_initial_equity(10000.0)
        # Fill heat above the new 4% threshold: add 4.2% heat
        rm.on_position_opened(risk_amount=420, account_balance=10000.0)
        # Now any additional position should push over 4% limit
        # Note: the existing heat (4.2%) already exceeds 4.0% max, so
        # can_add_position will return False even for 0 risk
        # But the sizer will produce a lot > 0 with entry=2050, SL=2045 (dist=5)
        result = run_approve(rm)
        assert result.approved is False
        assert "heat" in result.reason.lower()

    def test_rejected_when_equity_curve_filter_blocks(self):
        rm = make_rm(equity_curve_ema_period=5)
        rm.set_initial_equity(10000.0)
        # Seed EMA high
        for _ in range(5):
            rm.equity_filter.update(11000.0)
        # Drop equity well below EMA
        for _ in range(3):
            rm.equity_filter.update(9000.0)
        result = run_approve(rm)
        assert result.approved is False
        assert "equity" in result.reason.lower()

    def test_approved_with_high_confidence(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        result = run_approve(rm, confidence=0.9)
        assert result.approved is True

    def test_approved_with_low_confidence_uses_smaller_sizing(self):
        rm = make_rm()
        rm.set_initial_equity(10000.0)
        rm.update_trade_stats(win_rate=0.6, avg_win=3.0, avg_loss=1.0)
        high_result = run_approve(rm, confidence=0.9)
        low_result = run_approve(rm, confidence=0.3)
        # Low confidence should produce same or smaller lot than high confidence
        assert low_result.lot_size <= high_result.lot_size

    def test_rejects_trade_when_final_advanced_size_breaks_heat_limit(self):
        rm = make_rm(max_portfolio_heat_pct=5.0)
        rm.set_initial_equity(10000.0)
        rm.update_trade_stats(win_rate=0.9, avg_win=4.0, avg_loss=1.0)

        result = run_approve(
            rm,
            confidence=0.95,
            atr=0.5,
            entry_price=2050.0,
            stop_loss=1950.0,
        )

        assert result.approved is False
        assert "heat" in result.reason.lower()


# ---------------------------------------------------------------------------
# Tests: disabled equity filter
# ---------------------------------------------------------------------------

class TestDisabledEquityFilter:
    def test_disabled_filter_does_not_block_trades(self):
        rm = make_rm(equity_curve_ema_period=5, equity_curve_filter_enabled=False)
        rm.set_initial_equity(10000.0)
        # Artificially drop equity below would-be EMA
        for _ in range(5):
            rm.equity_filter.update(11000.0)
        for _ in range(3):
            rm.equity_filter.update(9000.0)
        # Even though equity is below EMA, filter is disabled
        assert rm.is_trading_allowed() is True
        result = run_approve(rm)
        assert result.approved is True
