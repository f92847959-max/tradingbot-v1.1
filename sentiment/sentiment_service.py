"""Background news sentiment service."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database.connection import get_session
from sentiment.news_fetcher import FeedFetcher, GOLD_FEEDS
from sentiment.seed_writer import write_sentiment_seed
from sentiment.sentiment_aggregator import SentimentAggregator
from sentiment.sentiment_analyzer import SentimentAnalyzer
from sentiment.sentiment_repository import SentimentRepository

logger = logging.getLogger(__name__)


class SentimentService:
    """Poll news feeds, score articles, persist rows, and refresh MiroFish seed."""

    def __init__(self, settings: Any, seed_path: str | Path = "mirofish_seeds/news_sentiment.md") -> None:
        self.settings = settings
        self._fetcher = FeedFetcher(
            source_weights=getattr(settings, "sentiment_source_weights", None),
            min_keywords=getattr(settings, "sentiment_min_keywords", 1),
        )
        self._analyzer = SentimentAnalyzer(
            model=getattr(settings, "sentiment_model", "vader"),
            finbert_cache_path=getattr(settings, "sentiment_finbert_cache_path", ""),
        )
        self._aggregator = SentimentAggregator(
            repository=None,
            halflife_minutes=getattr(settings, "sentiment_halflife_minutes", 30),
        )
        self._seed_path = Path(seed_path)
        self._scheduler: AsyncIOScheduler | None = None
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_seed_write: datetime | None = None

    @property
    def aggregator(self) -> SentimentAggregator:
        return self._aggregator

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self.poll_once,
            "interval",
            seconds=getattr(self.settings, "sentiment_poll_interval_seconds", 300),
            id="sentiment_poll",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.add_job(
            self._maybe_write_seed,
            "interval",
            hours=getattr(self.settings, "sentiment_seed_update_hours", 1),
            id="sentiment_seed",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        logger.info(
            "News sentiment service ENABLED (poll every %ds)",
            getattr(self.settings, "sentiment_poll_interval_seconds", 300),
        )

    async def stop(self) -> None:
        self._running = False
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("News sentiment service stopped")

    async def poll_once(self) -> int:
        scored_articles: list[dict[str, Any]] = []
        for source, url in GOLD_FEEDS.items():
            try:
                articles = await self._fetcher.poll_feed(source, url)
            except Exception as exc:
                logger.warning("Sentiment feed poll failed for %s: %s", source, exc)
                continue
            for article in articles:
                text = f"{article.get('headline', '')} {article.get('summary', '')}"
                article["sentiment_score"] = self._analyzer.score(text)
                article["model_used"] = getattr(self.settings, "sentiment_model", "vader")
                scored_articles.append(article)

        if not scored_articles:
            return 0

        async with get_session() as session:
            repository = SentimentRepository(session)
            await repository.save_batch(
                scored_articles,
                model_used=getattr(self.settings, "sentiment_model", "vader"),
            )
        await self._maybe_write_seed()
        return len(scored_articles)

    async def _maybe_write_seed(self) -> None:
        now = datetime.now(timezone.utc)
        cadence = timedelta(hours=getattr(self.settings, "sentiment_seed_update_hours", 1))
        if self._last_seed_write is not None and now - self._last_seed_write < cadence:
            return
        async with get_session() as session:
            repository = SentimentRepository(session)
            records = await repository.get_records(now - timedelta(hours=24), now, limit=10)
        write_sentiment_seed(records, self._seed_path, now)
        self._last_seed_write = now
