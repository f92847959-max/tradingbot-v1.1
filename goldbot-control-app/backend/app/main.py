"""FastAPI entrypoint for the control app backend."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.auth import verify_access_token
from backend.app.config import load_settings
from backend.app.database import init_db
from backend.app.rate_limit import AuthRateLimitMiddleware
from backend.app.routers import bot, health, logs, settings, trades
from backend.app.services import build_control_service


def create_app() -> FastAPI:
    """Create and configure FastAPI app instance."""
    init_db()
    app_settings = load_settings()

    app = FastAPI(
        title="GoldBot Control API",
        description="Local control-plane API for monitoring and manual command execution.",
        version="0.1.0",
    )
    app.state.control_service = build_control_service()

    # Rate limit authenticated endpoints (10 requests/min/IP) to mitigate
    # token brute-force attempts against the X-Control-Token header.
    app.add_middleware(
        AuthRateLimitMiddleware,
        max_requests=10,
        window_seconds=60,
        protected_prefix="/api/v1",
        exempt_paths=("/api/v1/health",),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Control-Token"],
    )

    protected = [Depends(verify_access_token)]

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(bot.router, prefix="/api/v1", dependencies=protected)
    app.include_router(logs.router, prefix="/api/v1", dependencies=protected)
    app.include_router(settings.router, prefix="/api/v1", dependencies=protected)
    app.include_router(trades.router, prefix="/api/v1", dependencies=protected)

    @app.get("/")
    def root() -> dict:
        return {
            "service": "goldbot-control-api",
            "docs": "/docs",
            "api_base": "/api/v1",
            "host": app_settings.api_host,
            "port": app_settings.api_port,
        }

    return app


app = create_app()
