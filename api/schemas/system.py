"""Pydantic schemas for system / health endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    timestamp: datetime
    uptime_seconds: float
    version: str = "1.0.0"


class ComponentStatus(BaseModel):
    name: str
    status: Literal["ok", "error", "unknown"]
    detail: str = ""


class SystemStatusResponse(BaseModel):
    trading_active: bool
    mode: Literal["demo", "live"]
    kill_switch_active: bool
    current_drawdown_pct: float
    daily_loss_pct: float
    equity_peak: float
    open_positions: int
    trades_today: int
    uptime_seconds: float
    components: list[ComponentStatus]


class KillSwitchRequest(BaseModel):
    activate: bool
    reason: str = "manual"
