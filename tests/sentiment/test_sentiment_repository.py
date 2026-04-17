"""RED tests for SENT-05 -- filled in by Plan 11-02."""
import pytest


@pytest.mark.asyncio
async def test_save_and_load(sentiment_session):
    pytest.fail("Wave 0 red test -- insert+query in Plan 11-02")


@pytest.mark.asyncio
async def test_dedup(sentiment_session):
    pytest.fail("Wave 0 red test -- entry_id unique constraint in Plan 11-02")


@pytest.mark.asyncio
async def test_query_window(sentiment_session):
    pytest.fail("Wave 0 red test -- time-window query in Plan 11-02")


@pytest.mark.asyncio
async def test_retention_cleanup(sentiment_session):
    pytest.fail("Wave 0 red test -- 30-day retention deletes in Plan 11-02")
