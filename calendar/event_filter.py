"""Gold-relevant economic event filter.

Retains only events that can meaningfully move XAUUSD price:
- Events from countries whose monetary policy affects Gold (USD, EUR, etc.)
- Events matching Gold-specific keywords (NFP, FOMC, CPI, etc.)
- Medium and High impact only (Low impact rarely moves Gold, unless keyword match)
"""

import logging

from calendar.models import EconomicEvent, EventImpact

logger = logging.getLogger(__name__)

# Countries whose monetary policy directly affects Gold price
GOLD_RELEVANT_COUNTRIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CNY"}

# Keywords for Gold-specific events (case-insensitive matching)
GOLD_KEYWORDS = {
    "nonfarm",
    "non-farm",
    "nfp",
    "fomc",
    "fed",
    "federal reserve",
    "interest rate",
    "cpi",
    "consumer price",
    "inflation",
    "gdp",
    "gross domestic",
    "ppi",
    "producer price",
    "retail sales",
    "unemployment",
    "jobless",
    "pmi",
    "purchasing manager",
    "ecb",
    "boe",
    "boj",
    "gold",
    "comex",
    "cot report",
    "central bank",
    "monetary policy",
    "treasury",
    "bond",
    "yield",
}


def filter_gold_relevant(events: list[EconomicEvent]) -> list[EconomicEvent]:
    """Keep only events relevant to Gold/XAUUSD trading.

    Relevance criteria:
    1. Country in GOLD_RELEVANT_COUNTRIES, OR
    2. Title contains a GOLD_KEYWORDS match
    AND: High or Medium impact only (Low impact rarely moves Gold).
    """
    filtered: list[EconomicEvent] = []
    for event in events:
        # Skip low-impact unless it matches Gold keywords
        title_lower = event.title.lower()
        has_gold_keyword = any(kw in title_lower for kw in GOLD_KEYWORDS)

        if event.impact == EventImpact.LOW and not has_gold_keyword:
            continue

        if event.country in GOLD_RELEVANT_COUNTRIES or has_gold_keyword:
            filtered.append(event)

    logger.info(
        "Filtered %d/%d events as Gold-relevant", len(filtered), len(events)
    )
    return filtered
