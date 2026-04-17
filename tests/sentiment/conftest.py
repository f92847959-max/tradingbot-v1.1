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
async def sentiment_session():
    """In-memory SQLite async session for sentiment repository tests.

    Uses pytest asyncio_mode='auto' (configured in pyproject.toml) -- no explicit
    pytest_asyncio import needed.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from database.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()
