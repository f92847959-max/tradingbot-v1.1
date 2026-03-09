"""Shared Pydantic contracts for control app APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CommandType(StrEnum):
    """Supported manual control commands."""

    START_BOT = "START_BOT"
    STOP_BOT = "STOP_BOT"
    RELOAD_CONFIG = "RELOAD_CONFIG"
    PAUSE_TRADING = "PAUSE_TRADING"
    RESUME_TRADING = "RESUME_TRADING"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class BotState(StrEnum):
    """Current control-plane state."""

    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"


class CommandRequest(BaseModel):
    """Command payload accepted by POST /bot/commands."""

    command_id: str = Field(min_length=3, max_length=64)
    command_type: CommandType
    target: str | None = Field(default=None, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(default="local-user", min_length=1, max_length=64)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirm_token: str | None = Field(default=None, max_length=64)


class CommandResponse(BaseModel):
    """Result of a submitted command."""

    accepted: bool
    command_id: str
    command_type: CommandType
    status: str
    message: str
    executed_at: datetime


class BotStatusResponse(BaseModel):
    """Current bot state and heartbeat."""

    state: BotState
    uptime_sec: int
    last_heartbeat: datetime
    active_strategy: str
    open_positions: int
    risk_state: str
    last_error: str | None = None


class BotMetricsResponse(BaseModel):
    """Operational metrics for dashboard polling."""

    orders_today: int
    successful_commands_24h: int
    failed_commands_24h: int
    api_latency_ms: float
    db_latency_ms: float


class ActionLogEntry(BaseModel):
    """Action log record."""

    id: int
    command_id: str
    command_type: CommandType
    target: str | None = None
    params: dict[str, Any]
    status: str
    message: str
    requested_by: str
    requested_at: datetime
    executed_at: datetime


class ErrorLogEntry(BaseModel):
    """Error log record."""

    id: int
    source: str
    error_code: str
    message: str
    details: str
    created_at: datetime


class LogsResponse(BaseModel):
    """Generic list response for action/error logs."""

    items: list[ActionLogEntry] | list[ErrorLogEntry]


class SettingsResponse(BaseModel):
    """Control app settings."""

    polling_interval_seconds: int = Field(ge=2, le=5)
    confirmations_enabled: bool = True
    updated_at: datetime


class SettingsUpdateRequest(BaseModel):
    """Patch payload for settings update."""

    polling_interval_seconds: int | None = Field(default=None, ge=2, le=5)
    confirmations_enabled: bool | None = None


class TradeChartPoint(BaseModel):
    """Single trade point for entry/SL/TP visualization."""

    id: int
    deal_id: str | None = None
    opened_at: datetime
    closed_at: datetime | None = None
    direction: str
    status: str
    entry_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    exit_price: float | None = None
    lot_size: float | None = None
    net_pnl: float | None = None
