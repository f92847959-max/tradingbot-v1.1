"""Async repository for NewsSentiment rows."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import NewsSentiment


class SentimentRepository:
    """Persist and query scored news sentiment records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_one(
        self,
        article: dict[str, Any],
        sentiment_score: float | None = None,
        model_used: str = "vader",
    ) -> NewsSentiment:
        existing = await self.get_by_entry_id(str(article["entry_id"]))
        if existing is not None:
            return existing

        row = NewsSentiment(
            published_at=article["published_at"],
            source=article["source"],
            headline=article["headline"],
            summary=article.get("summary"),
            url=article.get("url"),
            entry_id=str(article["entry_id"]),
            sentiment_score=float(
                sentiment_score
                if sentiment_score is not None
                else article.get("sentiment_score", 0.0)
            ),
            source_weight=float(article.get("source_weight", 1.0)),
            keywords_matched=article.get("keywords_matched"),
            model_used=model_used,
        )
        self._session.add(row)
        try:
            await self._session.commit()
            await self._session.refresh(row)
            return row
        except IntegrityError:
            await self._session.rollback()
            existing = await self.get_by_entry_id(str(article["entry_id"]))
            if existing is None:
                raise
            return existing

    async def save_batch(
        self,
        articles: list[dict[str, Any]],
        model_used: str = "vader",
    ) -> list[NewsSentiment]:
        rows = []
        for article in articles:
            rows.append(await self.save_one(article, model_used=model_used))
        return rows

    async def get_by_entry_id(self, entry_id: str) -> NewsSentiment | None:
        result = await self._session.execute(
            select(NewsSentiment).where(NewsSentiment.entry_id == entry_id)
        )
        return result.scalar_one_or_none()

    async def get_records(
        self,
        start: datetime,
        end: datetime,
        limit: int | None = None,
    ) -> list[NewsSentiment]:
        stmt = (
            select(NewsSentiment)
            .where(NewsSentiment.published_at >= start)
            .where(NewsSentiment.published_at <= end)
            .order_by(NewsSentiment.published_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def prune_older_than(self, cutoff: datetime) -> int:
        result = await self._session.execute(
            delete(NewsSentiment).where(NewsSentiment.published_at < cutoff)
        )
        await self._session.commit()
        return int(result.rowcount or 0)
