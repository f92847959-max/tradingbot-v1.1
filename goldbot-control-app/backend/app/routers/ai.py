"""AI decision-stack endpoint for the Mission-Control UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.dependencies import get_control_service
from backend.app.services import ControlService
from shared.contracts import AIDecisionResponse

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/decisions/latest", response_model=AIDecisionResponse)
def get_latest_ai_decision(
    service: ControlService = Depends(get_control_service),
) -> AIDecisionResponse:
    """Snapshot of the current AI decision-stack (core / specialist / exit / risk)."""
    return service.get_ai_decision()
