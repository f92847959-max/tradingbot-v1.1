"""Settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_control_service
from backend.app.services import ControlService
from shared.contracts import SettingsResponse, SettingsUpdateRequest

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
def get_settings(service: ControlService = Depends(get_control_service)) -> SettingsResponse:
    """Read current settings."""
    return service.get_settings()


@router.put("", response_model=SettingsResponse)
def update_settings(
    payload: SettingsUpdateRequest,
    service: ControlService = Depends(get_control_service),
) -> SettingsResponse:
    """Update mutable settings."""
    return service.update_settings(payload)

