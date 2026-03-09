from datetime import datetime, timezone

import pytest

from backend.app.guards import GuardViolation, validate_command_guard
from shared.contracts import CommandRequest, CommandType


def make_command(command_type: CommandType, confirm_token: str | None = None) -> CommandRequest:
    return CommandRequest(
        command_id="cmd-123",
        command_type=command_type,
        target="trading-engine",
        params={},
        requested_by="tester",
        requested_at=datetime.now(timezone.utc),
        confirm_token=confirm_token,
    )


def test_non_critical_command_does_not_require_confirm() -> None:
    command = make_command(CommandType.PAUSE_TRADING)
    validate_command_guard(command, confirmations_enabled=True)


def test_critical_command_requires_confirm() -> None:
    command = make_command(CommandType.STOP_BOT, confirm_token=None)
    with pytest.raises(GuardViolation):
        validate_command_guard(command, confirmations_enabled=True)


def test_critical_command_accepts_confirm_token() -> None:
    command = make_command(CommandType.STOP_BOT, confirm_token="CONFIRM")
    validate_command_guard(command, confirmations_enabled=True)

