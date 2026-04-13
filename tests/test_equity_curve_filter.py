"""Tests for EquityCurveFilter -- Phase 9 Plan 03."""

import pytest

from risk.equity_curve_filter import EquityCurveFilter


class TestEquityCurveFilterInit:
    def test_init_defaults(self):
        ecf = EquityCurveFilter()
        assert ecf.ema_period == 20
        assert ecf.enabled is True

    def test_init_custom_period(self):
        ecf = EquityCurveFilter(ema_period=10)
        assert ecf.ema_period == 10

    def test_init_disabled(self):
        ecf = EquityCurveFilter(enabled=False)
        assert ecf.enabled is False

    def test_initial_state_is_allowed(self):
        ecf = EquityCurveFilter()
        assert ecf.is_trading_allowed() is True


class TestInsufficientData:
    def test_allowed_with_fewer_than_period_points(self):
        ecf = EquityCurveFilter(ema_period=20)
        for i in range(19):
            ecf.update(10000 + i)
        assert ecf.is_trading_allowed() is True

    def test_get_equity_vs_ema_with_insufficient_data(self):
        ecf = EquityCurveFilter(ema_period=20)
        ecf.update(10000)
        assert ecf.get_equity_vs_ema() == "insufficient_data"


class TestEMACalculation:
    def test_ema_seeded_after_period_points(self):
        ecf = EquityCurveFilter(ema_period=5)
        for i in range(5):
            ecf.update(10000.0)
        assert ecf.get_ema() == pytest.approx(10000.0)

    def test_rising_equity_above_ema_allows_trading(self):
        ecf = EquityCurveFilter(ema_period=5)
        # Seed with stable values
        for _ in range(5):
            ecf.update(10000.0)
        # Add rising values
        ecf.update(10500.0)
        assert ecf.is_trading_allowed() is True
        assert ecf.get_equity_vs_ema() == "above"

    def test_equity_below_ema_blocks_trading(self):
        ecf = EquityCurveFilter(ema_period=5)
        # Seed EMA high
        for _ in range(5):
            ecf.update(11000.0)
        # Then drop equity significantly below EMA
        for _ in range(3):
            ecf.update(9000.0)
        assert ecf.is_trading_allowed() is False
        assert ecf.get_equity_vs_ema() == "below"

    def test_update_returns_is_trading_allowed(self):
        ecf = EquityCurveFilter(ema_period=5)
        for _ in range(4):
            ecf.update(10000.0)
        result = ecf.update(10000.0)  # 5th point seeds EMA
        assert isinstance(result, bool)


class TestDisabledFilter:
    def test_disabled_always_allows_trading(self):
        ecf = EquityCurveFilter(ema_period=5, enabled=False)
        # Even with equity below EMA
        for _ in range(5):
            ecf.update(11000.0)
        for _ in range(3):
            ecf.update(9000.0)
        assert ecf.is_trading_allowed() is True

    def test_disabled_still_updates_ema(self):
        ecf = EquityCurveFilter(ema_period=5, enabled=False)
        for _ in range(5):
            ecf.update(10000.0)
        assert ecf.get_ema() == pytest.approx(10000.0)


class TestReset:
    def test_reset_clears_history_and_ema(self):
        ecf = EquityCurveFilter(ema_period=5)
        for _ in range(5):
            ecf.update(10000.0)
        ecf.reset()
        assert ecf._equity_history == []
        assert ecf._ema == 0.0
        assert ecf.is_trading_allowed() is True

    def test_reset_allows_trading_again_after_block(self):
        ecf = EquityCurveFilter(ema_period=5)
        for _ in range(5):
            ecf.update(11000.0)
        for _ in range(3):
            ecf.update(9000.0)
        assert ecf.is_trading_allowed() is False
        ecf.reset()
        assert ecf.is_trading_allowed() is True


class TestGetEma:
    def test_get_ema_returns_zero_before_seeding(self):
        ecf = EquityCurveFilter(ema_period=5)
        assert ecf.get_ema() == 0.0

    def test_get_ema_returns_float(self):
        ecf = EquityCurveFilter(ema_period=5)
        for _ in range(5):
            ecf.update(10000.0)
        assert isinstance(ecf.get_ema(), float)
