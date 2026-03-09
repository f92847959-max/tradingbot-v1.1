"""Market data routers: price, candles, signal, model info, session."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_trading_system, get_db
from api.schemas.market import (
    CandleResponse,
    PriceResponse,
    SignalResponse,
    ModelInfoResponse,
    SessionResponse,
)
from database.repositories.candle_repo import CandleRepository
from database.repositories.signal_repo import SignalRepository
from market_data.broker_client import BrokerError
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/price", response_model=PriceResponse)
async def get_price(system=Depends(get_trading_system)) -> PriceResponse:
    """Get current XAU/USD bid/ask price from Capital.com."""
    try:
        price_data = await system.data.get_current_price()
    except BrokerError as e:
        raise HTTPException(status_code=502, detail=f"Broker error: {e}")

    bid = price_data.get("bid", 0.0)
    ask = price_data.get("ask", 0.0)
    mid = (bid + ask) / 2 if bid and ask else 0.0
    spread = round(ask - bid, 2) if ask and bid else 0.0

    return PriceResponse(
        symbol="XAU/USD",
        bid=bid,
        ask=ask,
        mid=round(mid, 2),
        spread=spread,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/candles", response_model=list[CandleResponse])
async def get_candles(
    timeframe: str = Query(default="5m", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    count: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> list[CandleResponse]:
    """Get OHLCV candles for XAU/USD from database."""
    repo = CandleRepository(db)
    candles = await repo.get_latest(timeframe=timeframe, count=count)
    return [
        CandleResponse(
            timestamp=c.timestamp,
            open=float(c.open),
            high=float(c.high),
            low=float(c.low),
            close=float(c.close),
            volume=float(c.volume) if c.volume else 0.0,
        )
        for c in candles
    ]


@router.get("/signal", response_model=SignalResponse | None)
async def get_last_signal(db: AsyncSession = Depends(get_db)) -> SignalResponse | None:
    """Return the most recent AI signal from database."""
    repo = SignalRepository(db)
    signals = await repo.get_latest(count=1)
    if not signals:
        return None
    s = signals[0]
    return SignalResponse(
        action=s.action,
        confidence=float(s.confidence),
        entry_price=float(s.entry_price) if s.entry_price else 0.0,
        stop_loss=float(s.stop_loss) if s.stop_loss else None,
        take_profit=float(s.take_profit) if s.take_profit else None,
        trade_score=s.trade_score,
        method=s.reasoning.get("method", "unknown") if s.reasoning else "unknown",
        timestamp=s.timestamp,
    )


@router.get("/model-info", response_model=ModelInfoResponse)
async def get_model_info(system=Depends(get_trading_system)) -> ModelInfoResponse:
    """Return AI model training status."""
    predictor = system._ai_predictor
    if predictor is None:
        return ModelInfoResponse(
            xgboost_trained=False,
            lightgbm_trained=False,
            lstm_trained=False,
            last_trained_at=None,
            total_predictions=0,
            accuracy_7d=None,
        )

    ensemble = getattr(predictor, "ensemble", None)
    if ensemble is None:
        return ModelInfoResponse(
            xgboost_trained=False,
            lightgbm_trained=False,
            lstm_trained=False,
            last_trained_at=None,
            total_predictions=0,
            accuracy_7d=None,
        )

    return ModelInfoResponse(
        xgboost_trained=getattr(ensemble, "_xgb_loaded", False),
        lightgbm_trained=getattr(ensemble, "_lgb_loaded", False),
        lstm_trained=getattr(ensemble, "_lstm_loaded", False),
        last_trained_at=None,
        total_predictions=getattr(predictor, "_prediction_count", 0),
        accuracy_7d=None,
    )


@router.get("/session", response_model=SessionResponse)
async def get_session_info() -> SessionResponse:
    """Return current trading session info."""
    from datetime import time as dt_time
    now_utc = datetime.now(timezone.utc)
    # London/Frankfurt session: 07:00–16:00 UTC (09:00–18:00 MEZ)
    session_start = dt_time(7, 0)
    session_end = dt_time(16, 0)
    current_time = now_utc.time().replace(tzinfo=None)
    is_active = (
        now_utc.weekday() < 5  # Mon–Fri
        and session_start <= current_time <= session_end
    )
    return SessionResponse(
        session_name="London/Frankfurt",
        is_active=is_active,
        start_time="07:00 UTC",
        end_time="16:00 UTC",
        current_time_utc=now_utc.strftime("%H:%M UTC"),
    )
