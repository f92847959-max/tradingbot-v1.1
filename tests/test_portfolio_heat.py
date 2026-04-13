"""Tests for PortfolioHeatManager -- Phase 9 Plan 03."""

import pytest

from risk.portfolio_heat import PortfolioHeatManager


class TestPortfolioHeatManagerInit:
    def test_init_defaults(self):
        mgr = PortfolioHeatManager()
        assert mgr.max_heat_pct == 5.0

    def test_init_custom_max(self):
        mgr = PortfolioHeatManager(max_heat_pct=3.0)
        assert mgr.max_heat_pct == 3.0

    def test_initial_heat_is_zero(self):
        mgr = PortfolioHeatManager()
        assert mgr.get_heat(10000.0) == 0.0

    def test_initial_open_risk_is_zero(self):
        mgr = PortfolioHeatManager()
        assert mgr._open_risk_total == 0.0


class TestAddPosition:
    def test_add_single_position_updates_heat(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        mgr.add_position(risk_amount=200, account_balance=10000)
        assert mgr.get_heat(10000) == pytest.approx(2.0)

    def test_add_two_positions_accumulates(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        mgr.add_position(risk_amount=200, account_balance=10000)
        mgr.add_position(risk_amount=300, account_balance=10000)
        assert mgr.get_heat(10000) == pytest.approx(5.0)

    def test_add_position_with_zero_balance(self):
        mgr = PortfolioHeatManager()
        mgr.add_position(risk_amount=200, account_balance=0)
        assert mgr.get_heat(0) == 0.0


class TestRemovePosition:
    def test_remove_position_decreases_heat(self):
        mgr = PortfolioHeatManager()
        mgr.add_position(risk_amount=200, account_balance=10000)
        mgr.remove_position(risk_amount=200, account_balance=10000)
        assert mgr.get_heat(10000) == pytest.approx(0.0)

    def test_remove_partial_position(self):
        mgr = PortfolioHeatManager()
        mgr.add_position(risk_amount=500, account_balance=10000)
        mgr.remove_position(risk_amount=200, account_balance=10000)
        assert mgr.get_heat(10000) == pytest.approx(3.0)

    def test_heat_never_goes_negative(self):
        mgr = PortfolioHeatManager()
        mgr.add_position(risk_amount=100, account_balance=10000)
        mgr.remove_position(risk_amount=500, account_balance=10000)  # Remove more than added
        assert mgr.get_heat(10000) == pytest.approx(0.0)
        assert mgr._open_risk_total == 0.0


class TestCanAddPosition:
    def test_can_add_when_below_max(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        result = mgr.can_add_position(risk_amount=100, account_balance=10000)
        assert result is True  # 1% < 5%

    def test_cannot_add_when_would_exceed_max(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        mgr.add_position(risk_amount=400, account_balance=10000)  # heat = 4%
        result = mgr.can_add_position(risk_amount=200, account_balance=10000)  # would be 6%
        assert result is False

    def test_can_add_exactly_at_max(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        result = mgr.can_add_position(risk_amount=500, account_balance=10000)  # exactly 5%
        assert result is True

    def test_cannot_add_with_zero_balance(self):
        mgr = PortfolioHeatManager()
        result = mgr.can_add_position(risk_amount=100, account_balance=0)
        assert result is False


class TestGetRemainingHeat:
    def test_full_capacity_when_no_positions(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        remaining = mgr.get_remaining_heat(account_balance=10000)
        assert remaining == pytest.approx(500.0)  # 5% of 10000

    def test_remaining_decreases_as_heat_grows(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        mgr.add_position(risk_amount=200, account_balance=10000)
        remaining = mgr.get_remaining_heat(account_balance=10000)
        assert remaining == pytest.approx(300.0)  # 500 - 200

    def test_remaining_is_zero_at_max_heat(self):
        mgr = PortfolioHeatManager(max_heat_pct=5.0)
        mgr.add_position(risk_amount=500, account_balance=10000)
        remaining = mgr.get_remaining_heat(account_balance=10000)
        assert remaining == pytest.approx(0.0)


class TestReset:
    def test_reset_clears_positions(self):
        mgr = PortfolioHeatManager()
        mgr.add_position(risk_amount=400, account_balance=10000)
        mgr.reset()
        assert mgr._open_risk_total == 0.0
        assert mgr.get_heat(10000) == 0.0
