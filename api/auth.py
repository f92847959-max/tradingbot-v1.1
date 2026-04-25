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

    # Hard cap on tracked IPs to prevent unbounded memory growth.
    _MAX_TRACKED_IPS = 500

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, client_ip: str) -> bool:
        """Returns True if request is allowed."""
        now = time.monotonic()
        timestamps = self._requests[client_ip]
        # Prune old entries for this IP
        fresh = [t for t in timestamps if now - t < self.window]
        if len(fresh) >= self.max_requests:
            # Persist the pruned list and reject
            self._requests[client_ip] = fresh
            return False
        fresh.append(now)
        self._requests[client_ip] = fresh

        # Per-request cleanup: if this slot is empty, drop it from the dict.
        if not self._requests[client_ip]:
            try:
                del self._requests[client_ip]
            except KeyError:
                pass

        # Hard cap on tracked IPs with LRU-ish eviction (drop oldest last-seen).
        if len(self._requests) > self._MAX_TRACKED_IPS:
            try:
                victim = min(
                    self._requests.items(),
                    key=lambda kv: kv[1][-1] if kv[1] else 0,
                )[0]
                del self._requests[victim]
            except (ValueError, KeyError):
                pass

        return True


# ---------------------------------------------------------------------------
# Global rate limiter for order / mutating endpoints
# ---------------------------------------------------------------------------

order_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)


async def check_order_rate_limit(request: Request) -> None:
    """FastAPI dependency for rate-limiting order / mutating endpoints.

    Applied to POST endpoints that can move money or flip kill switches
    (e.g. /positions/close, /positions/close-all, /risk/kill-switch).
    """
    client_ip = request.client.host if request.client else "unknown"
    if not order_rate_limiter.check(client_ip):
        logger.warning("Rate limit exceeded for %s on %s", client_ip, request.url.path)
        raise HTTPException(status_code=429, detail="Rate limit exceeded (max 10 requests/minute)")
