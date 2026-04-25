"""Tests for smart exit trailing and partial-close management."""

import pytest

from exit_engine import (
    PartialCloseManager,
    SmartTrailingManager,
    calculate_trailing_stop,
    evaluate_partial_close,
    profit_r_multiple,
)


class TestProfitRMultiple:
    def test_buy_profit_r(self):
        assert profit_r_multiple("BUY", 2000.0, 2006.0, 1994.0) == 1.0

    def test_sell_profit_r(self):
        assert profit_r_multiple("SELL", 2000.0, 1994.0, 2006.0) == 1.0

    def test_zero_initial_risk_rejected(self):
        with pytest.raises(ValueError):
            profit_r_multiple("BUY", 2000.0, 2001.0, 2000.0)


class TestCalculateTrailingStop:
    def test_no_activation_before_one_r(self):
        result = calculate_trailing_stop(
            "BUY",
            entry_price=2000.0,
            current_price=2004.0,
            initial_stop_loss=1994.0,
            atr=2.0,
        )

        assert result.new_sl is None
        assert result.activated is False
        assert result.profit_r == pytest.approx(0.6667)

    def test_buy_activates_to_breakeven_at_one_r(self):
        result = calculate_trailing_stop(
            "BUY",
            entry_price=2000.0,
            current_price=2006.0,
            initial_stop_loss=1994.0,
            atr=10.0,
        )

        assert result.activated is True
        assert result.new_sl == 2000.0
        assert result.reason == "breakeven"

    def test_buy_trails_by_atr_after_profit_extends(self):
        result = calculate_trailing_stop(
            "BUY",
            entry_price=2000.0,
            current_price=2010.0,
            initial_stop_loss=1994.0,
            atr=2.0,
        )

        assert result.activated is True
        assert result.new_sl == 2008.0
        assert result.reason == "atr_trail"

    def test_buy_does_not_move_stop_down(self):
        result = calculate_trailing_stop(
            "BUY",
            entry_price=2000.0,
            current_price=2008.0,
            initial_stop_loss=1994.0,
            atr=2.0,
            current_stop_loss=2007.0,
        )

        assert result.activated is True
        assert result.new_sl is None
        assert result.reason == "no favorable SL improvement"

    def test_sell_trails_by_atr_after_profit_extends(self):
        result = calculate_trailing_stop(
            "SELL",
            entry_price=2000.0,
            current_price=1990.0,
            initial_stop_loss=2006.0,
            atr=2.0,
        )

        assert result.activated is True
        assert result.new_sl == 1992.0
        assert result.reason == "atr_trail"

    def test_sell_does_not_move_stop_up(self):
        result = calculate_trailing_stop(
            "SELL",
            entry_price=2000.0,
            current_price=1992.0,
            initial_stop_loss=2006.0,
            atr=2.0,
            current_stop_loss=1993.0,
        )

        assert result.activated is True
        assert result.new_sl is None


class TestSmartTrailingManager:
    def test_tracks_last_stop_per_deal(self):
        manager = SmartTrailingManager()
        first = manager.evaluate("D1", "BUY", 2000.0, 2010.0, 1994.0, atr=2.0)
        second = manager.evaluate("D1", "BUY", 2000.0, 2009.0, 1994.0, atr=2.0)

        assert first.new_sl == 2008.0
        assert second.new_sl is None
        assert manager.is_trailing_active("D1")

    def test_remove_tracking(self):
        manager = SmartTrailingManager()
        manager.evaluate("D1", "BUY", 2000.0, 2010.0, 1994.0, atr=2.0)
        manager.remove_tracking("D1")

        assert not manager.is_trailing_active("D1")


class TestEvaluatePartialClose:
    def test_no_action_before_tp1_for_buy(self):
        action = evaluate_partial_close("BUY", current_price=2004.0, tp1=2005.0)

        assert action.close_fraction == 0.0
        assert action.target_hit == "none"

    def test_buy_closes_half_at_tp1(self):
        action = evaluate_partial_close("BUY", current_price=2005.0, tp1=2005.0)

        assert action.close_fraction == 0.5
        assert action.target_hit == "tp1"

    def test_sell_closes_half_at_tp1(self):
        action = evaluate_partial_close("SELL", current_price=1995.0, tp1=1995.0)

        assert action.close_fraction == 0.5
        assert action.target_hit == "tp1"

    def test_no_duplicate_action_after_already_closed(self):
        action = evaluate_partial_close(
            "BUY",
            current_price=2006.0,
            tp1=2005.0,
            already_closed=True,
        )

        assert action.close_fraction == 0.0
        assert action.reason == "tp1 already closed"


class TestPartialCloseManager:
    def test_manager_fires_once_per_deal(self):
        manager = PartialCloseManager(close_fraction=0.5)

        first = manager.evaluate("D1", "BUY", current_price=2005.0, tp1=2005.0)
        second = manager.evaluate("D1", "BUY", current_price=2006.0, tp1=2005.0)

        assert first.close_fraction == 0.5
        assert second.close_fraction == 0.0
        assert manager.was_tp1_closed("D1")

    def test_remove_tracking_allows_new_lifecycle(self):
        manager = PartialCloseManager(close_fraction=0.5)
        manager.evaluate("D1", "BUY", current_price=2005.0, tp1=2005.0)
        manager.remove_tracking("D1")

        assert not manager.was_tp1_closed("D1")
