"""Action and error log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.dependencies import get_control_service
from backend.app.services import ControlService
from shared.contracts import ActionLogEntry, ErrorLogEntry

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/actions", response_model=list[ActionLogEntry])
def list_actions(
    limit: int = Query(default=100, ge=1, le=500),
    service: ControlService = Depends(get_control_service),
) -> list[ActionLogEntry]:
    """List recent action logs in descending order."""
    return service.list_actions(limit=limit)


@router.get("/errors", response_model=list[ErrorLogEntry])
def list_errors(
    limit: int = Query(default=100, ge=1, le=500),
    service: ControlService = Depends(get_control_service),
) -> list[ErrorLogEntry]:
    """List recent error logs in descending order."""
    return service.list_errors(limit=limit)

