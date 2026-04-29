from types import SimpleNamespace

import pytest

from sentiment.news_fetcher import FeedFetcher


def test_filter_gold_relevant_articles(sample_feed_bytes):
    articles = FeedFetcher(min_keywords=1).filter_entries(sample_feed_bytes, "kitco")

    assert [article["entry_id"] for article in articles] == [
        "test-gold-surges-001",
        "test-gold-slides-001",
    ]
    assert all(article["published_at"].tzinfo is not None for article in articles)
    assert all(article["source"] == "kitco" for article in articles)


def test_keyword_match_min_threshold(sample_feed_bytes):
    articles = FeedFetcher(min_keywords=3).filter_entries(sample_feed_bytes, "kitco")

    assert len(articles) == 2
    assert all(len(article["keywords_matched"]) >= 3 for article in articles)


@pytest.mark.asyncio
async def test_etag_caching_returns_304(monkeypatch):
    calls = []

    class DummyFeedparser:
        @staticmethod
        def parse(url, etag=None, modified=None):
            calls.append((url, etag, modified))
            if etag == "abc":
                return SimpleNamespace(status=304, entries=[])
            return SimpleNamespace(status=200, etag="abc", entries=[])

    import sentiment.news_fetcher as news_fetcher

    monkeypatch.setattr(news_fetcher, "feedparser", DummyFeedparser)
    fetcher = FeedFetcher()

    assert await fetcher.poll_feed("kitco", "https://example.com/feed") == []
    assert await fetcher.poll_feed("kitco", "https://example.com/feed") == []
    assert calls[1][1] == "abc"


def test_url_normalization_strips_utm(sample_feed_bytes):
    articles = FeedFetcher().filter_entries(sample_feed_bytes, "kitco")

    assert articles[0]["url"] == "https://example.com/gold-surges"
