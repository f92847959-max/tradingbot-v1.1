"""Trade chart endpoints for entry/SL/TP visualization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_control_service
from backend.app.services import ControlService
from shared.contracts import TradeChartPoint

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/chart", response_model=list[TradeChartPoint])
def trade_chart_points(
    days: int = Query(default=14, ge=1, le=365),
    limit: int = Query(default=400, ge=1, le=2000),
    service: ControlService = Depends(get_control_service),
) -> list[TradeChartPoint]:
    """Return chart-ready trade points with entry, stop-loss and take-profit."""
    return service.get_trade_chart_points(days=days, limit=limit)

