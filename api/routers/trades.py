"""Trade and position routers."""

import logging
from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import check_order_rate_limit
from api.dependencies import get_trading_system, get_db
from api.schemas.trades import (
    TradeResponse,
    PositionResponse,
    ClosePositionRequest,
    ClosePositionResponse,
    TradeSummaryResponse,
)
from database.repositories.trade_repo import TradeRepository
from market_data.broker_client import BrokerError

logger = logging.getLogger(__name__)
router = APIRouter()


def _trade_to_schema(trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        deal_id=trade.deal_id,
        direction=trade.direction,
        entry_price=float(trade.entry_price),
        exit_price=float(trade.exit_price) if trade.exit_price else None,
        lot_size=float(trade.lot_size),
        net_pnl=float(trade.net_pnl) if trade.net_pnl is not None else None,
        pnl_pips=float(trade.pnl_pips) if trade.pnl_pips is not None else None,
        close_reason=trade.close_reason,
        status=trade.status,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        ai_confidence=float(trade.ai_confidence) if trade.ai_confidence is not None else None,
        trade_score=trade.trade_score,
        reasoning=trade.reasoning,
    )


@router.get("/positions", response_model=list[PositionResponse])
async def get_positions(system=Depends(get_trading_system)) -> list[PositionResponse]:
    """List all currently open positions from Capital.com."""
    try:
        positions = await system.broker.get_positions()
    except BrokerError as e:
        raise HTTPException(status_code=502, detail=f"Broker error: {e}")

    result = []
    for pos in positions:
        from datetime import datetime as _dt
        opened_at = _dt.now(timezone.utc)
        if pos.created_at:
            try:
                opened_at = _dt.fromisoformat(pos.created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        result.append(
            PositionResponse(
                deal_id=pos.deal_id,
                direction=pos.direction,
                size=pos.size,
                entry_price=pos.open_level,
                current_price=pos.current_level,
                unrealized_pnl=pos.profit,
                stop_loss=pos.stop_level,
                take_profit=pos.limit_level,
                opened_at=opened_at,
            )
        )
    return result


@router.post(
    "/positions/close",
    response_model=ClosePositionResponse,
    dependencies=[Depends(check_order_rate_limit)],
)
async def close_position(
    request: ClosePositionRequest,
    system=Depends(get_trading_system),
) -> ClosePositionResponse:
    """Close a specific position by deal_id."""
    try:
        success = await system.orders.close_trade(request.deal_id, reason="MANUAL_API")
        return ClosePositionResponse(
            success=success,
            deal_id=request.deal_id,
            message="Position closed successfully" if success else "Failed to close position",
        )
    except BrokerError as e:
        raise HTTPException(status_code=502, detail=f"Broker error: {e}")
    except Exception as e:
        logger.error("Unhandled error while closing position %s: %s", request.deal_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post(
    "/positions/close-all",
    dependencies=[Depends(check_order_rate_limit)],
)
async def close_all_positions(system=Depends(get_trading_system)) -> dict:
    """Close all open positions immediately."""
    try:
        await system.orders.close_all()
        return {"success": True, "message": "Close-all request sent to broker"}
    except BrokerError as e:
        raise HTTPException(status_code=502, detail=f"Broker error: {e}")


@router.get("/history", response_model=list[TradeResponse])
async def trade_history(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
) -> list[TradeResponse]:
    """Return trade history for the last N days from database."""
    repo = TradeRepository(db)
    trades = await repo.get_history(days=days)
    return [_trade_to_schema(t) for t in trades]


@router.get("/summary", response_model=TradeSummaryResponse)
async def trade_summary(
    db: AsyncSession = Depends(get_db),
    system=Depends(get_trading_system),
) -> TradeSummaryResponse:
    """Return today's trade summary with P&L."""
    repo = TradeRepository(db)
    open_trades = await repo.get_open_trades()
    all_trades = await repo.get_all(limit=200)
    today_pnl = await repo.get_today_pnl()

    closed = [t for t in all_trades if t.status == "CLOSED" and t.net_pnl is not None]
    winners = [t for t in closed if float(t.net_pnl) > 0]
    win_rate = len(winners) / len(closed) if closed else 0.0

    return TradeSummaryResponse(
        total_trades=len(all_trades),
        open_trades=len(open_trades),
        today_pnl=round(today_pnl, 2) if today_pnl is not None else 0.0,
        today_trades=await repo.count_today(),
        win_rate=round(win_rate, 3),
        trades=[_trade_to_schema(t) for t in all_trades[:20]],
    )
