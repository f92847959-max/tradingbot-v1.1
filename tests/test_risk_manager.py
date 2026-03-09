import pytest
import asyncio

from risk.risk_manager import RiskManager


@pytest.mark.asyncio
async def test_approve_trade_basic_pass():
    rm = RiskManager(
        max_risk_per_trade_pct=1.0,
        max_daily_loss_pct=5.0,
        max_open_positions=3,
    )
    rm.set_initial_equity(10000.0)

    result = await rm.approve_trade(
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
    )

    assert result.approved is True


@pytest.mark.asyncio
async def test_reject_when_kill_switch_active():
    rm = RiskManager(kill_switch_drawdown_pct=20.0)
    rm.kill_switch.activate("test")

    result = await rm.approve_trade(
        direction="BUY",
        entry_price=2050.0,
        stop_loss=2045.0,
        current_equity=8000.0,
        available_margin=5000.0,
        open_positions=0,
        trades_today=0,
        consecutive_losses=0,
        current_spread=0.5,
        has_open_same_direction=False,
    )

    assert result.approved is False
