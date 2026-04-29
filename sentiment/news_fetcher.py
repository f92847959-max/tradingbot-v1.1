"""RSS feed fetching and gold relevance filtering."""

from __future__ import annotations

import asyncio
import calendar
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from xml.etree import ElementTree

try:
    import feedparser  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised implicitly in lean envs
    feedparser = None  # type: ignore


GOLD_FEEDS = {
    "kitco": "https://www.kitco.com/news/category/commodities/gold/rss",
    "investing": "https://www.investing.com/rss/news_11.rss",
    "marketwatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "goldbroker": "https://www.goldbroker.com/news.rss",
}

SOURCE_WEIGHTS = {
    "kitco": 1.0,
    "investing": 0.9,
    "marketwatch": 0.8,
    "goldbroker": 0.7,
}

GOLD_KEYWORDS = frozenset({
    "gold",
    "xauusd",
    "xau",
    "federal reserve",
    "fed ",
    "inflation",
    "cpi",
    "fomc",
    "interest rate",
    "dollar",
    "dxy",
    "central bank",
    "sanctions",
    "geopolit",
    "war",
    "conflict",
    "treasury yield",
    "precious metal",
    "safe haven",
    "safe-haven",
    "gold reserves",
    "bullion",
    "spot gold",
    "rate cut",
    "rate hike",
    "hawkish",
    "dovish",
    "easing",
    "tightening",
})

_UTM_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: str | None) -> str:
    return " ".join(_HTML_TAG_RE.sub(" ", value or "").split())


def _normalize_url(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _UTM_PARAMS
    ]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _count_keyword_matches(text: str) -> list[str]:
    lower = text.lower()
    return sorted(keyword for keyword in GOLD_KEYWORDS if keyword in lower)


def _parse_published(entry: Any) -> datetime:
    parsed_time = _entry_get(entry, "published_parsed") or _entry_get(entry, "updated_parsed")
    if parsed_time:
        return datetime.fromtimestamp(calendar.timegm(parsed_time), tz=timezone.utc)
    raw = _entry_get(entry, "published") or _entry_get(entry, "updated")
    if raw:
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(raw)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


def _entry_get(entry: Any, key: str, default: Any = None) -> Any:
    if isinstance(entry, dict):
        return entry.get(key, default)
    getter = getattr(entry, "get", None)
    if callable(getter):
        return getter(key, default)
    return getattr(entry, key, default)


def _parse_xml_feed(feed_bytes: bytes) -> SimpleNamespace:
    root = ElementTree.fromstring(feed_bytes)
    entries: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        entry = {
            "title": item.findtext("title", default=""),
            "summary": item.findtext("description", default=""),
            "link": item.findtext("link", default=""),
            "id": item.findtext("guid", default=""),
            "published": item.findtext("pubDate", default=""),
        }
        entries.append(entry)
    return SimpleNamespace(entries=entries)


def _parse_feed_bytes(feed_bytes: bytes) -> Any:
    if feedparser is not None:
        return feedparser.parse(feed_bytes)
    return _parse_xml_feed(feed_bytes)


class FeedFetcher:
    """Fetch RSS feeds and filter entries to gold-relevant articles."""

    def __init__(
        self,
        source_weights: dict[str, float] | None = None,
        min_keywords: int = 1,
    ) -> None:
        self._etags: dict[str, str] = {}
        self._modified: dict[str, str] = {}
        self._weights = source_weights or SOURCE_WEIGHTS
        self._min_keywords = min_keywords

    def filter_entries(
        self,
        feed_bytes: bytes,
        source: str,
        feed_url: str = "",
    ) -> list[dict[str, Any]]:
        parsed = _parse_feed_bytes(feed_bytes)
        return self._filter_parsed(parsed, source, feed_url=feed_url)

    async def poll_feed(self, source: str, url: str) -> list[dict[str, Any]]:
        if feedparser is None:
            return []

        loop = asyncio.get_running_loop()
        parsed = await loop.run_in_executor(
            None,
            lambda: feedparser.parse(
                url,
                etag=self._etags.get(source),
                modified=self._modified.get(source),
            ),
        )
        if getattr(parsed, "status", None) == 304:
            return []
        if getattr(parsed, "etag", None):
            self._etags[source] = parsed.etag
        if getattr(parsed, "modified", None):
            self._modified[source] = parsed.modified
        return self._filter_parsed(parsed, source, feed_url=url)

    def _filter_parsed(
        self,
        parsed: Any,
        source: str,
        feed_url: str = "",
    ) -> list[dict[str, Any]]:
        articles: list[dict[str, Any]] = []
        for entry in getattr(parsed, "entries", []):
            headline = _entry_get(entry, "title", "")
            summary = _strip_html(_entry_get(entry, "summary", "") or _entry_get(entry, "description", ""))
            matched = _count_keyword_matches(f"{headline} {summary}")
            if len(matched) < self._min_keywords:
                continue

            raw_url = _entry_get(entry, "link", "") or feed_url
            normalized_url = _normalize_url(raw_url)
            entry_id = (
                _entry_get(entry, "id")
                or _entry_get(entry, "guid")
                or normalized_url
                or f"{source}:{headline}:{_parse_published(entry).isoformat()}"
            )
            articles.append({
                "source": source,
                "headline": headline,
                "summary": summary,
                "url": normalized_url,
                "entry_id": entry_id,
                "published_at": _parse_published(entry),
                "keywords_matched": matched,
                "source_weight": self._weights.get(source, 0.5),
            })
        return articles
