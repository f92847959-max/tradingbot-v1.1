"""Adapter between control app and the existing gold_bot domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared.contracts import BotState, CommandType


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class BotRuntimeState:
    """In-memory runtime state; replace internals with real domain wiring."""

    started_at: datetime = field(default_factory=utc_now)
    state: BotState = BotState.STOPPED
    active_strategy: str = "xau-usd-intraday-v1"
    open_positions: int = 0
    risk_state: str = "normal"
    last_error: str | None = None
    orders_today: int = 0
    successful_commands_24h: int = 0
    failed_commands_24h: int = 0


class GoldBotAdapter:
    """Thin adapter API consumed by the backend service layer."""

    def __init__(self) -> None:
        self._state = BotRuntimeState()

    def get_status(self) -> dict:
        """Fetch current status from bot runtime."""
        return {
            "state": self._state.state,
            "uptime_sec": int((utc_now() - self._state.started_at).total_seconds()),
            "last_heartbeat": utc_now(),
            "active_strategy": self._state.active_strategy,
            "open_positions": self._state.open_positions,
            "risk_state": self._state.risk_state,
            "last_error": self._state.last_error,
        }

    def get_metrics(self) -> dict:
        """Fetch dashboard metrics."""
        return {
            "orders_today": self._state.orders_today,
            "successful_commands_24h": self._state.successful_commands_24h,
            "failed_commands_24h": self._state.failed_commands_24h,
            "api_latency_ms": 18.4,
            "db_latency_ms": 4.9,
        }

    def execute_command(self, command_type: CommandType, target: str | None, params: dict) -> str:
        """Execute a supported command against the runtime.

        This default implementation keeps the system safe and local-only.
        Swap internals with real trading system calls when ready.
        """
        del target, params
        if command_type == CommandType.START_BOT:
            self._state.state = BotState.RUNNING
            self._state.risk_state = "normal"
            self._state.successful_commands_24h += 1
            return "Bot gestartet."

        if command_type == CommandType.STOP_BOT:
            self._state.state = BotState.STOPPED
            self._state.successful_commands_24h += 1
            return "Bot gestoppt."

        if command_type == CommandType.PAUSE_TRADING:
            self._state.state = BotState.PAUSED
            self._state.successful_commands_24h += 1
            return "Trading pausiert."

        if command_type == CommandType.RESUME_TRADING:
            self._state.state = BotState.RUNNING
            self._state.risk_state = "normal"
            self._state.successful_commands_24h += 1
            return "Trading fortgesetzt."

        if command_type == CommandType.RELOAD_CONFIG:
            self._state.successful_commands_24h += 1
            return "Konfiguration neu geladen."

        if command_type == CommandType.EMERGENCY_STOP:
            self._state.state = BotState.STOPPED
            self._state.risk_state = "emergency_stop"
            self._state.successful_commands_24h += 1
            return "Not-Aus ausgeführt."

        self._state.failed_commands_24h += 1
        self._state.last_error = f"Unknown command: {command_type}"
        raise ValueError(f"Unsupported command type: {command_type}")
