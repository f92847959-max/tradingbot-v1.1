"""Pydantic schemas for market data endpoints."""

from datetime import datetime

from pydantic import BaseModel


class CandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class PriceResponse(BaseModel):
    symbol: str
    bid: float
    ask: float
    mid: float
    spread: float
    timestamp: datetime


class SignalResponse(BaseModel):
    action: str
    confidence: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    trade_score: int | None
    method: str
    timestamp: datetime


class ModelInfoResponse(BaseModel):
    xgboost_trained: bool
    lightgbm_trained: bool
    lstm_trained: bool
    last_trained_at: datetime | None
    total_predictions: int
    accuracy_7d: float | None


class SessionResponse(BaseModel):
    session_name: str
    is_active: bool
    start_time: str
    end_time: str
    current_time_utc: str
