"""Unit tests for the risk management module."""

import pytest
from datetime import datetime, time

from risk.kill_switch import KillSwitch
from risk.position_sizing import PositionSizer
from risk.pre_trade_check import PreTradeChecker, CheckResult
from risk.risk_manager import RiskManager


# ---------------------------------------------------------------------------
# KillSwitch Tests
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_initially_inactive(self):
        ks = KillSwitch()
        assert ks.is_active is False
        assert ks.reason == ""

    def test_activate(self):
        ks = KillSwitch()
        ks.activate("test reason")
        assert ks.is_active is True
        assert ks.reason == "test reason"

    def test_activate_twice_no_change(self):
        ks = KillSwitch()
        ks.activate("first")
        ks.activate("second")
        assert ks.reason == "first"  # Second activate ignored

    def test_deactivate(self):
        ks = KillSwitch()
        ks.activate("test")
        ks.deactivate()
        assert ks.is_active is False
        assert ks.reason == ""

    def test_deactivate_when_inactive_safe(self):
        ks = KillSwitch()
        ks.deactivate()  # Should not raise
        assert ks.is_active is False

    def test_check_drawdown_triggers(self):
        ks = KillSwitch(max_drawdown_pct=20.0)
        triggered = ks.check_drawdown(21.0)
        assert triggered is True
        assert ks.is_active is True

    def test_check_drawdown_below_threshold(self):
        ks = KillSwitch(max_drawdown_pct=20.0)
        triggered = ks.check_drawdown(19.9)
        assert triggered is False
        assert ks.is_active is False

    def test_check_drawdown_at_threshold(self):
        ks = KillSwitch(max_drawdown_pct=20.0)
        triggered = ks.check_drawdown(20.0)
        assert triggered is True

    def test_status_dict(self):
        ks = KillSwitch(max_drawdown_pct=15.0)
        status = ks.status()
        assert "active" in status
        assert "max_drawdown_pct" in status
        assert status["max_drawdown_pct"] == 15.0


# ---------------------------------------------------------------------------
# PositionSizer Tests
# ---------------------------------------------------------------------------

class TestPositionSizer:
    def test_basic_calculation(self):
        sizer = PositionSizer(risk_per_trade_pct=1.0, min_lot_size=0.01, max_lot_size=10.0)
        # equity=10000, risk=1%=100, sl_distance=2.0 → 100/2.0 = 50 lots → clamped to 10
        result = sizer.calculate(equity=10000, entry_price=2000.0, stop_loss=1998.0)
        assert result == 10.0  # clamped to max

    def test_small_position(self):
        sizer = PositionSizer(risk_per_trade_pct=1.0, min_lot_size=0.01, max_lot_size=10.0)
        # equity=1000, risk=1%=10, sl_distance=50 → 10/50 = 0.2 lots
        result = sizer.calculate(equity=1000, entry_price=2000.0, stop_loss=1950.0)
        assert result == 0.2

    def test_minimum_lot_when_sl_zero(self):
        sizer = PositionSizer(risk_per_trade_pct=1.0, min_lot_size=0.01)
        result = sizer.calculate(equity=10000, entry_price=2000.0, stop_loss=2000.0)
        assert result == 0.01

    def test_respects_min_lot(self):
        sizer = PositionSizer(risk_per_trade_pct=0.01, min_lot_size=0.01, max_lot_size=10.0)
        # Very small risk → should clamp to min
        result = sizer.calculate(equity=100, entry_price=2000.0, stop_loss=1990.0)
        assert result == 0.01

    def test_respects_max_lot(self):
        sizer = PositionSizer(risk_per_trade_pct=10.0, min_lot_size=0.01, max_lot_size=5.0)
        result = sizer.calculate(equity=100000, entry_price=2000.0, stop_loss=1999.0)
        assert result == 5.0

    def test_returns_rounded_to_2dp(self):
        sizer = PositionSizer(risk_per_trade_pct=1.0, min_lot_size=0.01, max_lot_size=10.0)
        result = sizer.calculate(equity=3333, entry_price=2000.0, stop_loss=1993.0)
        assert result == round(result, 2)


# ---------------------------------------------------------------------------
# PreTradeChecker Tests
# ---------------------------------------------------------------------------

def _checker(**kwargs) -> PreTradeChecker:
    defaults = dict(
        max_daily_loss_pct=5.0,
        max_weekly_loss_pct=10.0,
        max_open_positions=3,
        max_trades_per_day=80,
        max_consecutive_losses=5,
        cooldown_minutes=30,
        max_spread=5.0,
        kill_switch_drawdown_pct=20.0,
        trading_start=time(8, 0),
        trading_end=time(22, 0),
    )
    defaults.update(kwargs)
    return PreTradeChecker(**defaults)


def _run_all(checker: PreTradeChecker, **overrides) -> list[CheckResult]:
    defaults = dict(
        kill_switch_active=False,
        current_time=datetime(2024, 1, 15, 12, 0),  # Monday noon UTC
        daily_loss_pct=0.0,
        weekly_loss_pct=0.0,
        open_positions=0,
        trades_today=0,
        consecutive_losses=0,
        last_loss_time=None,
        current_spread=1.0,
        available_margin=10000.0,
        required_margin=100.0,
        has_open_same_direction=False,
        current_drawdown_pct=0.0,
    )
    defaults.update(overrides)
    return checker.run_all(**defaults)


def _get(results: list[CheckResult], name: str) -> CheckResult:
    return next(r for r in results if r.check_name == name)


class TestPreTradeChecker:
    def test_all_pass_nominal(self):
        checker = _checker()
        results = _run_all(checker)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 0

    def test_kill_switch_blocks(self):
        checker = _checker()
        results = _run_all(checker, kill_switch_active=True)
        assert not _get(results, "kill_switch").passed

    def test_weekend_blocks(self):
        checker = _checker()
        saturday = datetime(2024, 1, 13, 12, 0)  # Saturday
        results = _run_all(checker, current_time=saturday)
        assert not _get(results, "trading_hours").passed

    def test_outside_hours_blocks(self):
        checker = _checker()
        early = datetime(2024, 1, 15, 5, 0)  # 05:00 UTC
        results = _run_all(checker, current_time=early)
        assert not _get(results, "trading_hours").passed

    def test_daily_loss_limit(self):
        checker = _checker(max_daily_loss_pct=5.0)
        results = _run_all(checker, daily_loss_pct=5.0)
        assert not _get(results, "daily_loss").passed

    def test_daily_loss_under_limit(self):
        checker = _checker(max_daily_loss_pct=5.0)
        results = _run_all(checker, daily_loss_pct=4.9)
        assert _get(results, "daily_loss").passed

    def test_weekly_loss_limit(self):
        checker = _checker(max_weekly_loss_pct=10.0)
        results = _run_all(checker, weekly_loss_pct=10.0)
        assert not _get(results, "weekly_loss").passed

    def test_max_positions_reached(self):
        checker = _checker(max_open_positions=3)
        results = _run_all(checker, open_positions=3)
        assert not _get(results, "max_positions").passed

    def test_max_trades_today_reached(self):
        checker = _checker(max_trades_per_day=80)
        results = _run_all(checker, trades_today=80)
        assert not _get(results, "max_trades_today").passed

    def test_loss_streak_with_cooldown(self):
        checker = _checker(max_consecutive_losses=3, cooldown_minutes=30)
        last_loss = datetime(2024, 1, 15, 11, 50)  # 10 min ago
        now = datetime(2024, 1, 15, 12, 0)
        results = _run_all(checker,
            current_time=now,
            consecutive_losses=3,
            last_loss_time=last_loss,
        )
        assert not _get(results, "loss_streak").passed

    def test_loss_streak_cooldown_passed(self):
        checker = _checker(max_consecutive_losses=3, cooldown_minutes=30)
        last_loss = datetime(2024, 1, 15, 11, 0)  # 60 min ago — cooldown passed
        now = datetime(2024, 1, 15, 12, 0)
        results = _run_all(checker,
            current_time=now,
            consecutive_losses=3,
            last_loss_time=last_loss,
        )
        assert _get(results, "loss_streak").passed

    def test_spread_too_high(self):
        checker = _checker(max_spread=5.0)
        results = _run_all(checker, current_spread=5.1)
        assert not _get(results, "spread").passed

    def test_insufficient_margin(self):
        checker = _checker()
        results = _run_all(checker, available_margin=50.0, required_margin=100.0)
        assert not _get(results, "margin").passed

    def test_duplicate_direction_blocked(self):
        checker = _checker()
        results = _run_all(checker, has_open_same_direction=True)
        assert not _get(results, "duplicate").passed

    def test_drawdown_at_kill_switch_level(self):
        checker = _checker(kill_switch_drawdown_pct=20.0)
        results = _run_all(checker, current_drawdown_pct=20.0)
        assert not _get(results, "drawdown").passed


# ---------------------------------------------------------------------------
# RiskManager Integration Tests
# ---------------------------------------------------------------------------

class TestRiskManager:
    def _make(self, **kwargs) -> RiskManager:
        defaults = dict(
            max_risk_per_trade_pct=1.0,
            max_daily_loss_pct=5.0,
            max_weekly_loss_pct=10.0,
            max_open_positions=3,
            max_trades_per_day=80,
            kill_switch_drawdown_pct=20.0,
        )
        defaults.update(kwargs)
        return RiskManager(**defaults)

    @pytest.mark.asyncio
    async def test_approve_nominal(self, monkeypatch):
        from datetime import datetime, timezone
        # Freeze time to Monday noon so trading hours check passes
        monday_noon = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        monkeypatch.setattr("risk.risk_manager.datetime",
                            type("_dt", (), {"now": staticmethod(lambda tz=None: monday_noon)})())
        rm = self._make()
        rm.set_initial_equity(10000.0)
        result = await rm.approve_trade(
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1990.0,
            current_equity=10000.0,
            available_margin=5000.0,
            open_positions=0,
            trades_today=0,
            consecutive_losses=0,
            current_spread=1.0,
            has_open_same_direction=False,
        )
        assert result.approved is True
        assert result.lot_size > 0

    @pytest.mark.asyncio
    async def test_reject_kill_switch(self):
        rm = self._make()
        rm.set_initial_equity(10000.0)
        rm.kill_switch.activate("manual test")
        result = await rm.approve_trade(
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1990.0,
            current_equity=10000.0,
            available_margin=5000.0,
            open_positions=0,
            trades_today=0,
            consecutive_losses=0,
            current_spread=1.0,
            has_open_same_direction=False,
        )
        assert result.approved is False
        assert "kill_switch" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_reject_daily_loss(self):
        rm = self._make(max_daily_loss_pct=5.0)
        rm.set_initial_equity(10000.0)
        # Simulate 6% daily loss
        result = await rm.approve_trade(
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1990.0,
            current_equity=9400.0,  # 6% loss from 10000
            available_margin=5000.0,
            open_positions=0,
            trades_today=0,
            consecutive_losses=0,
            current_spread=1.0,
            has_open_same_direction=False,
        )
        assert result.approved is False
