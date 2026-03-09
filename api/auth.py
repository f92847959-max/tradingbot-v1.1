"""API authentication and rate limiting."""

import logging
import os
import secrets
import time
from collections import defaultdict

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

# API key header scheme
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _get_api_key() -> str:
    """Get the API key from environment or raise.

    Do NOT generate or log keys automatically. Require explicit configuration.
    """
    key = os.getenv("API_KEY")
    if not key:
        raise RuntimeError(
            "API_KEY not set. For local dev set API_KEY in your .env; "
            "for production use a Secrets Manager and set API_KEY env var."
        )
    return key


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(_api_key_header),
) -> str:
    """FastAPI dependency to verify API key on protected endpoints."""
    expected = _get_api_key()

    if not api_key:
        logger.warning("API request without key from %s: %s", request.client.host, request.url.path)
        raise HTTPException(status_code=401, detail="Missing API key (X-API-Key header)")

    # Use constant-time compare
    if not secrets.compare_digest(api_key, expected):
        logger.warning("Invalid API key from %s: %s", request.client.host, request.url.path)
        raise HTTPException(status_code=401, detail="Invalid API key")

    return api_key


# ---------------------------------------------------------------------------
# Rate Limiting
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple in-memory rate limiter per IP (best-effort).

    Note: For production use an external store (Redis) / robust limiter.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> bool:
        """Returns True if request is allowed."""
        now = time.monotonic()
        timestamps = self._requests[client_ip]
        # Prune old entries
        self._requests[client_ip] = [t for t in timestamps if now - t < self.window]
        if len(self._requests[client_ip]) >= self.max_requests:
            return False
        self._requests[client_ip].append(now)

        # Memory cleanup: cap tracked IPs at 2000 and prune stale
        if len(self._requests) > 2000:
            # Remove IPs with oldest last-access time (best-effort)
            items = list(self._requests.items())
            items.sort(key=lambda kv: kv[1][-1] if kv[1] else 0)
            for ip, _ in items[:500]:
                try:
                    del self._requests[ip]
                except KeyError:
                    pass

        return True
