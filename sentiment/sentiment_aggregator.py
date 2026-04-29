"""Aggregate scored news into ML-ready sentiment windows."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any


class SentimentAggregator:
    """Compute time-decayed sentiment features from news records."""

    def __init__(self, repository: Any | None = None, halflife_minutes: int = 30) -> None:
        self._repository = repository
        self._halflife_minutes = max(1, int(halflife_minutes))

    def get_features_at(
        self,
        now: datetime,
        window_records: list[Any] | None = None,
    ) -> dict[str, float]:
        records = window_records or []
        now = self._as_utc(now)
        sent_1h = self._window_score(records, now, timedelta(hours=1))
        sent_4h = self._window_score(records, now, timedelta(hours=4))
        sent_24h = self._window_score(records, now, timedelta(hours=24))
        return {
            "sent_1h": sent_1h,
            "sent_4h": sent_4h,
            "sent_24h": sent_24h,
            "sent_momentum": self._clamp(sent_1h - sent_4h),
            "news_count_1h": float(self._count_window(records, now, timedelta(hours=1))),
        }

    async def get_features_at_async(self, now: datetime) -> dict[str, float]:
        if self._repository is None:
            return self.get_features_at(now, [])
        now = self._as_utc(now)
        records = await self._repository.get_records(now - timedelta(hours=24), now)
        return self.get_features_at(now, records)

    def _window_score(
        self,
        records: list[Any],
        now: datetime,
        window: timedelta,
    ) -> float:
        in_window = [
            record for record in records
            if now - window <= self._published_at(record) <= now
        ]
        if not in_window:
            return 0.0

        weighted_sum = 0.0
        weight_sum = 0.0
        for record in in_window:
            age_minutes = max(0.0, (now - self._published_at(record)).total_seconds() / 60.0)
            decay = math.pow(0.5, age_minutes / self._halflife_minutes)
            weight = float(self._field(record, "source_weight", 1.0) or 1.0) * decay
            weighted_sum += float(self._field(record, "sentiment_score", 0.0) or 0.0) * weight
            weight_sum += weight
        return self._clamp(weighted_sum / weight_sum if weight_sum else 0.0)

    def _count_window(self, records: list[Any], now: datetime, window: timedelta) -> int:
        return sum(1 for record in records if now - window <= self._published_at(record) <= now)

    @staticmethod
    def _field(record: Any, name: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    @classmethod
    def _published_at(cls, record: Any) -> datetime:
        return cls._as_utc(cls._field(record, "published_at"))

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(-1.0, min(1.0, float(value)))
