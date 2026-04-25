"""Simple token-based auth for private control app APIs."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from backend.app.config import load_settings


def verify_access_token(x_control_token: str | None = Header(default=None)) -> None:
    """Verify request token from X-Control-Token header."""
    settings = load_settings()
    expected = settings.access_token.strip()
    provided = (x_control_token or "").strip()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server token configuration is missing.",
        )

    if not provided or not hmac.compare_digest(expected, provided):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nicht autorisiert. Bitte gueltigen Zugriffstoken senden.",
        )
