"""Pydantic schemas for trade and position endpoints."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class PositionResponse(BaseModel):
    deal_id: str
    direction: Literal["BUY", "SELL"]
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    stop_loss: float | None
    take_profit: float | None
    opened_at: datetime


class TradeResponse(BaseModel):
    id: int
    deal_id: str | None
    direction: Literal["BUY", "SELL"]
    entry_price: float
    exit_price: float | None
    lot_size: float
    net_pnl: float | None
    pnl_pips: float | None
    close_reason: str | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    ai_confidence: float | None
    trade_score: int | None
    reasoning: dict[str, Any] | None


class ClosePositionRequest(BaseModel):
    deal_id: str


class ClosePositionResponse(BaseModel):
    success: bool
    deal_id: str
    message: str


class TradeSummaryResponse(BaseModel):
    total_trades: int
    open_trades: int
    today_pnl: float
    today_trades: int
    win_rate: float
    trades: list[TradeResponse]
