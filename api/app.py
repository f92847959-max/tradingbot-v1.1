"""FastAPI application factory for the Gold Trading System REST API."""

import logging
import os
import time

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from api.auth import verify_api_key
from api.dependencies import set_trading_system
from api.routers import system as system_router
from api.routers import trades as trades_router
from api.routers import market as market_router
from api.routers import webhook as webhook_router

logger = logging.getLogger(__name__)

_START_TIME = time.monotonic()


def create_app(trading_system=None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        trading_system: The TradingSystem instance (optional at creation,
                        can be set later via set_trading_system()).
    """
    # Determine if API auth is enabled (default: true)
    auth_enabled = os.getenv("API_AUTH_ENABLED", "true").lower() in ("1", "true", "yes")

    # Build dependencies list — all protected routers require API key
    protected_deps = [Depends(verify_api_key)] if auth_enabled else []

    app = FastAPI(
        title="Gold Trading System API",
        description="REST API for monitoring and controlling the XAU/USD intraday trading system.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Audit logging middleware
    @app.middleware("http")
    async def audit_log_middleware(request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        client_ip = request.client.host if request.client else "unknown"
        logger.debug(
            "API %s %s from %s -> %d (%.3fs)",
            request.method, request.url.path, client_ip,
            response.status_code, duration,
        )
        return response

    # CORS — configure via environment variable CORS_ORIGINS (comma-separated)
    raw_origins = os.getenv("CORS_ORIGINS", "")
    if raw_origins:
        allow_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]
    else:
        # Default to localhost only
        allow_origins = ["http://127.0.0.1:3000", "http://127.0.0.1:5173"]
        logger.warning("CORS_ORIGINS not set — defaulting to localhost origins only")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Health endpoint — no auth required
    app.include_router(system_router.router, prefix="/api/v1", tags=["system"],
                       dependencies=protected_deps)
    app.include_router(market_router.router, prefix="/api/v1/market", tags=["market"],
                       dependencies=protected_deps)
    app.include_router(trades_router.router, prefix="/api/v1/orders", tags=["orders"],
                       dependencies=protected_deps)
    app.include_router(webhook_router.router, tags=["webhook"])

    # Inject trading system if provided at creation time
    if trading_system is not None:
        set_trading_system(trading_system)
        # Expose settings and optional confirmation handler on app.state for routers
        try:
            app.state.settings = trading_system.settings
            app.state.confirmation_handler = getattr(trading_system, "_confirmation_handler", None)
        except Exception:
            logger.debug("Failed to attach trading system state to app.state")

    return app
