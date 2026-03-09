"""Health and readiness endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Simple health check for local monitoring."""
    return {
        "status": "ok",
        "service": "goldbot-control-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

