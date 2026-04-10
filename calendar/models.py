"""Domain types for economic calendar events (pure Python, NOT ORM)."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class EventImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class EconomicEvent:
    title: str
    country: str  # "USD", "EUR", "GBP", "JPY"
    impact: EventImpact
    event_time: datetime  # UTC
    forecast: str | None = None
    previous: str | None = None
    actual: str | None = None
    id: int | None = None  # DB id, None if not persisted

    @property
    def is_high_impact(self) -> bool:
        return self.impact == EventImpact.HIGH

    @property
    def is_extreme(self) -> bool:
        """Extreme = high-impact USD event (NFP, FOMC, CPI)."""
        return self.is_high_impact and self.country == "USD"
