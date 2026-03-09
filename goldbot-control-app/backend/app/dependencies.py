"""FastAPI dependencies for router handlers."""

from __future__ import annotations

from fastapi import Request

from backend.app.services import ControlService


def get_control_service(request: Request) -> ControlService:
    """Read the service instance from FastAPI app state."""
    service = getattr(request.app.state, "control_service", None)
    if service is None:
        raise RuntimeError("Control service is not initialized.")
    return service

