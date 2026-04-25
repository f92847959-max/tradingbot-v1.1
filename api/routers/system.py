"""System routers: /health, /status, /risk/kill-switch."""

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from api.auth import check_order_rate_limit
from api.dependencies import get_trading_system, get_start_time, get_db
from api.schemas.system import (
    HealthResponse,
    SystemStatusResponse,
    ComponentStatus,
    KillSwitchRequest,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    db: AsyncSession = Depends(get_db),
    start_time: float = Depends(get_start_time),
) -> HealthResponse:
    """System health check — verifies DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc, exc_info=True)
        db_ok = False

    status = "ok" if db_ok else "degraded"
    return HealthResponse(
        status=status,
        timestamp=datetime.now(timezone.utc),
        uptime_seconds=time.monotonic() - start_time,
    )


@router.get("/status", response_model=SystemStatusResponse)
async def status(
    system=Depends(get_trading_system),
    start_time: float = Depends(get_start_time),
) -> SystemStatusResponse:
    """Detailed system and trading status."""
    risk = system.risk
    ks = risk.kill_switch

    # Compute drawdown from last known equity (equity_peak is always available)
    equity_peak = risk._equity_peak

    components = [
        ComponentStatus(
            name="broker",
            status="ok" if getattr(system.broker, "_cst", None) else "error",
            detail="authenticated" if getattr(system.broker, "_cst", None) else "not authenticated",
        ),
        ComponentStatus(
            name="trading_loop",
            status="ok" if system._running else "error",
            detail="running" if system._running else "stopped",
        ),
    ]

    return SystemStatusResponse(
        trading_active=system._running,
        mode=system.config.get("mode", "demo"),
        kill_switch_active=ks.is_active,
        current_drawdown_pct=0.0,  # Requires live equity query; see /risk/status
        daily_loss_pct=0.0,        # Requires live equity query; see /risk/status
        equity_peak=round(equity_peak, 2),
        open_positions=system.orders.get_open_count(),
        trades_today=0,
        uptime_seconds=round(time.monotonic() - start_time, 1),
        components=components,
    )


@router.post(
    "/risk/kill-switch",
    dependencies=[Depends(check_order_rate_limit)],
)
async def toggle_kill_switch(
    request: KillSwitchRequest,
    system=Depends(get_trading_system),
) -> dict:
    """Manually activate or deactivate the kill switch."""
    ks = system.risk.kill_switch
    if request.activate:
        ks.activate(request.reason)
        return {"success": True, "active": True, "reason": request.reason}
    else:
        ks.deactivate()
        return {"success": True, "active": False, "reason": "manually deactivated"}


@router.get("/risk/status")
async def risk_status(system=Depends(get_trading_system)) -> dict:
    """Current risk state."""
    risk = system.risk
    ks = risk.kill_switch
    return {
        "kill_switch_active": ks.is_active,
        "kill_switch_reason": getattr(ks, "reason", None),
        "equity_peak": round(risk._equity_peak, 2),
        "equity_start": round(risk._equity_start, 2),
        "note": "drawdown and daily_loss require live equity — call broker separately",
    }


@router.post(
    "/system/stop",
    dependencies=[Depends(check_order_rate_limit)],
)
async def stop_system(system=Depends(get_trading_system)) -> dict:
    """Gracefully stop the trading system."""
    await system.stop()
    return {"success": True, "message": "Trading system stop requested"}
