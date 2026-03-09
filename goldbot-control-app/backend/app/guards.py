"""Soft guard checks for manual control commands."""

from __future__ import annotations

from shared.contracts import CommandRequest, CommandType


class GuardViolation(ValueError):
    """Raised when a command violates the configured safety policy."""


CRITICAL_COMMANDS = {
    CommandType.STOP_BOT,
    CommandType.RELOAD_CONFIG,
    CommandType.EMERGENCY_STOP,
}


def validate_command_guard(command: CommandRequest, confirmations_enabled: bool) -> None:
    """Validate soft-guard requirements for critical commands."""
    if not confirmations_enabled:
        return

    normalized_confirm = (command.confirm_token or "").strip().upper()
    if command.command_type in CRITICAL_COMMANDS and normalized_confirm != "CONFIRM":
        raise GuardViolation(
            "Critical command requires confirm_token='CONFIRM'."
        )
