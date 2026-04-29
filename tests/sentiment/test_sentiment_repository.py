from datetime import timedelta

import pytest

from sentiment.sentiment_repository import SentimentRepository


@pytest.mark.asyncio
async def test_save_and_load(sentiment_session, sample_articles):
    async with sentiment_session() as session:
        repo = SentimentRepository(session)
        row = await repo.save_one(sample_articles[0])

        loaded = await repo.get_by_entry_id(sample_articles[0]["entry_id"])
        assert loaded is not None
        assert loaded.id == row.id


@pytest.mark.asyncio
async def test_dedup(sentiment_session, sample_articles):
    async with sentiment_session() as session:
        repo = SentimentRepository(session)
        first = await repo.save_one(sample_articles[0])
        second = await repo.save_one(sample_articles[0])

        assert first.id == second.id


@pytest.mark.asyncio
async def test_query_window(sentiment_session, sample_articles, reference_now):
    async with sentiment_session() as session:
        repo = SentimentRepository(session)
        await repo.save_batch(sample_articles)

        rows = await repo.get_records(reference_now - timedelta(hours=4), reference_now)
        assert {row.entry_id for row in rows} == {
            "kitco-2026-04-16-001",
            "investing-2026-04-16-001",
            "marketwatch-2026-04-16-001",
            "kitco-2026-04-16-002",
        }


@pytest.mark.asyncio
async def test_retention_cleanup(sentiment_session, sample_articles, reference_now):
    async with sentiment_session() as session:
        repo = SentimentRepository(session)
        await repo.save_batch(sample_articles)

        deleted = await repo.prune_older_than(reference_now - timedelta(hours=12))
        rows = await repo.get_records(reference_now - timedelta(days=2), reference_now)
        assert deleted == 2
        assert len(rows) == 4
