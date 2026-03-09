"""Dependency injection for FastAPI routes.

The TradingSystem instance is injected here once the server starts.
All routers access it via get_trading_system().
"""

from typing import TYPE_CHECKING, AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session

if TYPE_CHECKING:
    from main import TradingSystem

# ---------------------------------------------------------------------------
# Global state — set by main.py when the API server starts
# ---------------------------------------------------------------------------

_trading_system: "TradingSystem | None" = None
_start_time: float = 0.0


def set_trading_system(system: "TradingSystem", start_time: float) -> None:
    """Called from main.py after TradingSystem is initialized."""
    global _trading_system, _start_time
    _trading_system = system
    _start_time = start_time


def get_trading_system() -> "TradingSystem":
    if _trading_system is None:
        raise HTTPException(status_code=503, detail="Trading system not initialized")
    return _trading_system


def get_start_time() -> float:
    return _start_time


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with get_session() as session:
        yield session
