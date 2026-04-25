"""Integration tests for Exit-AI application in OrderManager."""

from __future__ import annotations

import pytest

from market_data.broker_client import Position
from order_management.order_manager import OrderManager


class _BrokerStub:
    def __init__(self, positions):
        self.positions = positions

    async def get_positions(self):
        return self.positions


class _ExecutorStub:
    def __init__(self):
        self.modified = []
        self.partial = []

    async def modify_position(self, deal_id, stop_loss=None, take_profit=None):
        self.modified.append((deal_id, stop_loss, take_profit))

    async def partial_close_position(self, deal_id, close_fraction):
        self.partial.append((deal_id, close_fraction))


class _AdvisorStub:
    def __init__(self, recommendation):
        self.recommendation = recommendation

    def recommend(self, _snapshot):
        return self.recommendation


def _position() -> Position:
    return Position(
        deal_id="D1",
        direction="BUY",
        size=1.0,
        open_level=2050.0,
        current_level=2051.5,
        stop_level=2049.0,
        limit_level=2053.0,
    )


@pytest.mark.asyncio
async def test_tighten_stop_recommendation_routes_through_modify_path() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=True)
    manager.executor = _ExecutorStub()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    manager._exit_ai_advisor = _AdvisorStub(
        type(
            "Recommendation",
            (),
            {
                "to_dict": lambda self: {
                    "action": "TIGHTEN_SL",
                    "confidence": 0.8,
                    "reason": "atr_trail",
                    "proposed_stop_loss": 2050.4,
                    "close_fraction": 0.0,
                    "no_op": False,
                    "baseline_context": {},
                }
            },
        )()
    )
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()

    assert manager.executor.modified == [("D1", 2050.4, None)]


@pytest.mark.asyncio
async def test_partial_close_recommendation_is_applied_only_once() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=True)
    manager.executor = _ExecutorStub()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    manager._exit_ai_advisor = _AdvisorStub(
        type(
            "Recommendation",
            (),
            {
                "to_dict": lambda self: {
                    "action": "PARTIAL_CLOSE",
                    "confidence": 0.75,
                    "reason": "tp1 reached",
                    "proposed_stop_loss": None,
                    "close_fraction": 0.5,
                    "no_op": False,
                    "baseline_context": {},
                }
            },
        )()
    )
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()
    await manager.check_positions()

    assert manager.executor.partial == [("D1", 0.5)]


@pytest.mark.asyncio
async def test_full_exit_recommendation_routes_through_close_trade() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=True)
    manager.executor = _ExecutorStub()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    called = []

    async def _close_trade(deal_id, reason="MANUAL"):
        called.append((deal_id, reason))
        return True

    manager.close_trade = _close_trade  # type: ignore[assignment]
    manager._exit_ai_advisor = _AdvisorStub(
        type(
            "Recommendation",
            (),
            {
                "to_dict": lambda self: {
                    "action": "FULL_EXIT",
                    "confidence": 0.9,
                    "reason": "model_full_exit",
                    "proposed_stop_loss": None,
                    "close_fraction": 0.0,
                    "no_op": False,
                    "baseline_context": {},
                }
            },
        )()
    )
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()

    assert called == [("D1", "EXIT_AI_FULL_EXIT")]


@pytest.mark.asyncio
async def test_missing_advisor_preserves_existing_behavior() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=False)
    manager.executor = _ExecutorStub()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()

    assert manager.executor.modified == []
    assert manager.exit_ai_audit_log == []
