"""Bot control and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.dependencies import get_control_service
from backend.app.guards import GuardViolation
from backend.app.services import ControlService
from shared.contracts import BotMetricsResponse, BotStatusResponse, CommandRequest, CommandResponse

router = APIRouter(prefix="/bot", tags=["bot"])


@router.get("/status", response_model=BotStatusResponse)
def get_status(service: ControlService = Depends(get_control_service)) -> BotStatusResponse:
    """Get current bot status."""
    return service.get_status()


@router.get("/metrics", response_model=BotMetricsResponse)
def get_metrics(service: ControlService = Depends(get_control_service)) -> BotMetricsResponse:
    """Get current metrics."""
    return service.get_metrics()


@router.post("/commands", response_model=CommandResponse)
def submit_command(
    command: CommandRequest,
    service: ControlService = Depends(get_control_service),
) -> CommandResponse:
    """Submit a manual control command."""
    try:
        return service.submit_command(command)
    except GuardViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Command execution failed: {exc}",
        ) from exc

