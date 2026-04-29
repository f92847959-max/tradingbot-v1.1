"""Shared fixtures for sentiment pipeline tests."""
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_feed_bytes() -> bytes:
    return (FIXTURES_DIR / "sample_feed.xml").read_bytes()


@pytest.fixture
def sample_articles() -> list[dict]:
    data = json.loads((FIXTURES_DIR / "sample_articles.json").read_text())
    for a in data:
        a["published_at"] = datetime.fromisoformat(a["published_at"].replace("Z", "+00:00"))
    return data


@pytest.fixture
def reference_now() -> datetime:
    return datetime(2026, 4, 16, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sentiment_session():
    """In-memory SQLite async session factory for sentiment repository tests.

    The project has a fallback async test runner when pytest-asyncio is absent,
    but pytest itself cannot resolve async generator fixtures without the plugin.
    Return a session factory so tests create sessions inside their own event loop.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from database.models import Base

    async def _create():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
        return engine, SessionLocal

    engine, SessionLocal = asyncio.run(_create())
    try:
        yield SessionLocal
    finally:
        async def _close():
            await engine.dispose()

        asyncio.run(_close())
