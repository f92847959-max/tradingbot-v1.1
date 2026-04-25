"""Simple in-memory rate limiter for token-protected endpoints.

Designed for the local control app: a single-process FastAPI server with
low traffic. The limiter caps the number of requests per client IP within a
sliding window to slow down brute-force attempts against the access token.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding-window rate limiter for protected API routes."""

    def __init__(
        self,
        app,
        max_requests: int = 10,
        window_seconds: int = 60,
        protected_prefix: str = "/api/v1",
        exempt_paths: Iterable[str] = (),
    ) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._protected_prefix = protected_prefix
        self._exempt_paths = tuple(exempt_paths)
        self._buckets: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _client_ip(self, request: Request) -> str:
        client = request.client
        if client and client.host:
            return client.host
        return "unknown"

    def _is_protected(self, path: str) -> bool:
        if not path.startswith(self._protected_prefix):
            return False
        for exempt in self._exempt_paths:
            if path == exempt or path.startswith(exempt + "/"):
                return False
        return True

    def _allow(self, ip: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._buckets[ip]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self._max_requests:
                return False
            bucket.append(now)
            return True

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or not self._is_protected(request.url.path):
            return await call_next(request)

        ip = self._client_ip(request)
        if not self._allow(ip):
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(self._window_seconds)},
            )
        return await call_next(request)
