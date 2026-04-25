"""SQLAlchemy async engine and session management.

Supports both SQLite (default, no install needed) and PostgreSQL.
Set DATABASE_URL in .env to switch:
  - SQLite:      sqlite+aiosqlite:///data/gold_trader.db
  - PostgreSQL:  postgresql+asyncpg://user:pass@localhost:5432/gold_trader
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _sqlite_url() -> str:
    """Build a SQLite fallback URL."""
    db_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "gold_trader.db")
    return f"sqlite+aiosqlite:///{db_path}"


def _mask_db_url(url: str) -> str:
    """Return a URL safe for logging by masking any embedded password.

    Handles `scheme://user:password@host/...` and leaves SQLite paths intact.
    """
    if not url or "://" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1)
        if "@" not in rest:
            return url
        creds, tail = rest.split("@", 1)
        if ":" in creds:
            user, _ = creds.split(":", 1)
            return f"{scheme}://{user}:***@{tail}"
        return url
    except Exception:
        return f"{url.split('://', 1)[0]}://***"


def _build_url() -> str:
    """Build database URL from environment.

    Priority:
    1. DATABASE_URL if set (full connection string)
    2. POSTGRES_* variables if POSTGRES_PASSWORD is set
    3. SQLite fallback (no install needed)
    """
    # If explicitly requested, force SQLite fallback (useful for local testing)
    if os.getenv("SQLITE_FALLBACK", "false").lower() in ("1", "true", "yes"):
        if not _check_aiosqlite_available():
            raise RuntimeError(
                "SQLITE_FALLBACK=true gesetzt, aber 'aiosqlite' ist nicht installiert.\n"
                "Installiere mit: pip install aiosqlite"
            )
        logger.warning("SQLITE_FALLBACK enabled: using local SQLite database")
        return _sqlite_url()

    # Option 1: Explicit DATABASE_URL
    explicit_url = os.getenv("DATABASE_URL", "")
    if explicit_url:
        return explicit_url

    # Option 2: PostgreSQL from individual vars
    pg_password = os.getenv("POSTGRES_PASSWORD", "")
    environment = os.getenv("ENVIRONMENT", "development").lower()
    pg_host_set = bool(os.getenv("POSTGRES_HOST"))
    if not pg_password and environment != "development" and pg_host_set:
        raise RuntimeError(
            "POSTGRES_PASSWORD must be set in non-development environments. "
            f"ENVIRONMENT={environment!r}, POSTGRES_HOST is set but no password."
        )
    if pg_password:
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "gold_trader")
        user = os.getenv("POSTGRES_USER", "trader")
        return f"postgresql+asyncpg://{user}:{pg_password}@{host}:{port}/{db}"

    # Option 3: SQLite (default when no PostgreSQL configured)
    if not _check_aiosqlite_available():
        raise RuntimeError(
            "Keine Datenbank konfiguriert und 'aiosqlite' nicht installiert.\n"
            "Optionen:\n"
            "  1. pip install aiosqlite  (für lokale SQLite-DB)\n"
            "  2. POSTGRES_PASSWORD in .env setzen  (für PostgreSQL)"
        )
    return _sqlite_url()


def _is_sqlite() -> bool:
    return _build_url().startswith("sqlite")


def _check_aiosqlite_available() -> bool:
    """Check if aiosqlite is installed before attempting SQLite fallback."""
    try:
        import aiosqlite  # noqa: F401
        return True
    except ImportError:
        return False


def _reset_to_sqlite() -> None:
    """Force-reset engine to SQLite (used on PostgreSQL connection failure)."""
    global _engine, _session_factory

    if not _check_aiosqlite_available():
        raise RuntimeError(
            "SQLite-Fallback fehlgeschlagen: 'aiosqlite' ist nicht installiert.\n"
            "Installiere mit: pip install aiosqlite\n"
            "Oder stelle sicher, dass PostgreSQL erreichbar ist."
        )

    url = _sqlite_url()
    _engine = create_async_engine(
        url,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        connect_args={"check_same_thread": False},
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.warning("Database reset to SQLite: %s", _mask_db_url(url))


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        url = _build_url()
        if url.startswith("sqlite"):
            _engine = create_async_engine(
                url,
                echo=os.getenv("SQL_ECHO", "false").lower() == "true",
                connect_args={"check_same_thread": False},
            )
        else:
            _engine = create_async_engine(
                url,
                pool_size=10,
                max_overflow=5,
                pool_pre_ping=True,
                pool_timeout=30,
                pool_recycle=3600,
                echo=os.getenv("SQL_ECHO", "false").lower() == "true",
                connect_args={"timeout": 10, "command_timeout": 30},
            )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional session scope.

    Commits on success, rolls back and re-raises on any error.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as exc:
            await session.rollback()
            logger.debug("DB session rollback: %s", exc)
            raise


async def init_db() -> None:
    """Create all tables.

    Falls back to SQLite only if SQLITE_FALLBACK is explicitly enabled.
    Otherwise, raises on PostgreSQL connection failure for clear diagnostics.
    """
    from .models import Base

    engine = get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except (ConnectionRefusedError, OSError) as exc:
        fallback_enabled = os.getenv("SQLITE_FALLBACK", "false").lower() in (
            "1", "true", "yes",
        )

        if not fallback_enabled:
            logger.critical(
                "PostgreSQL nicht erreichbar: %s\n"
                "Optionen:\n"
                "  1. PostgreSQL starten\n"
                "  2. SQLITE_FALLBACK=true in .env setzen für lokale SQLite-DB\n"
                "  3. DATABASE_URL in .env auf eine erreichbare DB setzen",
                exc,
            )
            raise RuntimeError(
                f"Datenbank nicht erreichbar: {exc}. "
                "Setze SQLITE_FALLBACK=true in .env für lokalen Betrieb."
            ) from exc

        logger.warning(
            "PostgreSQL nicht erreichbar (%s), wechsle zu SQLite (SQLITE_FALLBACK=true)...",
            exc,
        )
        await engine.dispose()
        _reset_to_sqlite()
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(
            "SQLite-Datenbank erfolgreich initialisiert (Fallback). "
            "WARNUNG: Daten werden nicht zwischen Instanzen geteilt."
        )


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
