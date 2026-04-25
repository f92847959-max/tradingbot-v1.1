"""Tests for Exit-AI audit logging and reconciliation visibility."""

from __future__ import annotations

import pytest

from market_data.broker_client import BrokerError, Position
from order_management.order_manager import OrderManager


class _BrokerStub:
    def __init__(self, positions):
        self.positions = positions

    async def get_positions(self):
        return self.positions


class _FailingExecutor:
    async def modify_position(self, _deal_id, stop_loss=None, take_profit=None):
        raise BrokerError("modify failed")


class _AdvisorStub:
    def recommend(self, _snapshot):
        return type(
            "Recommendation",
            (),
            {
                "to_dict": lambda self: {
                    "action": "TIGHTEN_SL",
                    "confidence": 0.82,
                    "reason": "atr_trail",
                    "proposed_stop_loss": 2050.4,
                    "close_fraction": 0.0,
                    "no_op": False,
                    "baseline_context": {"baseline_trailing_reason": "atr_trail"},
                }
            },
        )()


def _position() -> Position:
    return Position(
        deal_id="D2",
        direction="BUY",
        size=1.0,
        open_level=2050.0,
        current_level=2051.2,
        stop_level=2049.0,
        limit_level=2053.0,
    )


@pytest.mark.asyncio
async def test_exit_ai_audit_payload_contains_baseline_recommendation_and_outcome() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=True)
    manager.executor = type(
        "Executor",
        (),
        {"modify_position": lambda self, deal_id, stop_loss=None, take_profit=None: None},
    )()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    manager._exit_ai_advisor = _AdvisorStub()
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()

    audit = manager.exit_ai_audit_log[-1]
    assert audit["status"] == "applied"
    assert audit["recommendation"]["action"] == "TIGHTEN_SL"
    assert audit["baseline_context"]["baseline_trailing_reason"] == "atr_trail"


@pytest.mark.asyncio
async def test_exit_ai_failure_branch_preserves_reconciliation_context() -> None:
    pos = _position()
    manager = OrderManager(_BrokerStub([pos]), exit_ai_enabled=True)
    manager.executor = _FailingExecutor()
    manager.trailing.calculate_new_sl = lambda _pos, _level: None
    manager._exit_ai_advisor = _AdvisorStub()
    manager.monitor.track_position(pos.deal_id, pos)

    await manager.check_positions()

    audit = manager.exit_ai_audit_log[-1]
    assert audit["status"] == "rejected"
    assert audit["error"] == "modify failed"
    assert manager.monitor.get_runtime_context("D2")["deal_id"] == "D2"
