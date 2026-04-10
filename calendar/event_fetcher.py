"""ForexFactory economic calendar fetcher.

Uses the free faireconomy.media JSON mirror of ForexFactory data.
No API key required.

NOTE: aiohttp is imported inside the async function to avoid a module naming
conflict -- our ``calendar/`` package shadows the stdlib ``calendar`` module
that aiohttp.cookiejar depends on at import time.
"""

import logging
from datetime import datetime, timezone

from calendar.models import EconomicEvent, EventImpact

logger = logging.getLogger(__name__)

FF_THIS_WEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

IMPACT_MAP = {
    "High": EventImpact.HIGH,
    "Medium": EventImpact.MEDIUM,
    "Low": EventImpact.LOW,
    "Holiday": EventImpact.LOW,
    # Some entries use "Non-Economic" or empty -- those are skipped
}


async def fetch_events_this_week(
    timeout_seconds: float = 30.0,
) -> list[EconomicEvent]:
    """Fetch this week's economic events from ForexFactory mirror API.

    Returns list of EconomicEvent domain objects. Never raises -- returns
    empty list on error.
    """
    # Deferred import: aiohttp uses stdlib ``calendar`` module internally.
    # Importing at module level fails because our ``calendar/`` package shadows
    # the stdlib one. Importing here (after our package is already loaded)
    # lets Python resolve aiohttp's internal import correctly via sys.modules.
    import aiohttp  # noqa: E402

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                FF_THIS_WEEK_URL,
                timeout=aiohttp.ClientTimeout(total=timeout_seconds),
            ) as resp:
                if resp.status != 200:
                    logger.warning("ForexFactory API returned %d", resp.status)
                    return []
                data = await resp.json()
    except Exception as e:
        logger.error("Failed to fetch ForexFactory calendar: %s", e)
        return []

    events: list[EconomicEvent] = []
    for item in data:
        try:
            impact_str = item.get("impact", "")
            impact = IMPACT_MAP.get(impact_str, None)
            if impact is None:
                continue  # Skip non-economic entries

            # Parse date: format is "YYYY-MM-DDTHH:MM:SS-04:00" or similar
            date_str = item.get("date", "")
            event_time = datetime.fromisoformat(
                date_str.replace("Z", "+00:00")
            )

            events.append(
                EconomicEvent(
                    title=item.get("title", "Unknown"),
                    country=item.get("country", ""),
                    impact=impact,
                    event_time=event_time,
                    forecast=item.get("forecast"),
                    previous=item.get("previous"),
                    actual=item.get("actual"),
                )
            )
        except (ValueError, KeyError) as e:
            logger.debug("Skipping malformed event: %s", e)
            continue

    logger.info("Fetched %d economic events from ForexFactory", len(events))
    return events
