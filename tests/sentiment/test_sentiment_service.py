from types import SimpleNamespace

import pytest

from sentiment.sentiment_service import SentimentService


@pytest.mark.asyncio
async def test_sentiment_service_starts_and_stops():
    settings = SimpleNamespace(
        sentiment_source_weights={"kitco": 1.0},
        sentiment_min_keywords=1,
        sentiment_model="vader",
        sentiment_finbert_cache_path="",
        sentiment_halflife_minutes=30,
        sentiment_poll_interval_seconds=60,
        sentiment_seed_update_hours=1,
    )
    service = SentimentService(settings)

    await service.start()
    assert service.running is True
    assert service._scheduler is not None
    assert service._scheduler.running is True
    await service.stop()
    assert service.running is False
