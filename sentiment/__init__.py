"""News sentiment pipeline public API."""

from sentiment.news_fetcher import FeedFetcher, GOLD_FEEDS, GOLD_KEYWORDS, SOURCE_WEIGHTS
from sentiment.sentiment_aggregator import SentimentAggregator
from sentiment.sentiment_analyzer import SentimentAnalyzer
from sentiment.sentiment_repository import SentimentRepository
from sentiment.sentiment_service import SentimentService

__all__ = [
    "FeedFetcher",
    "GOLD_FEEDS",
    "GOLD_KEYWORDS",
    "SOURCE_WEIGHTS",
    "SentimentAggregator",
    "SentimentAnalyzer",
    "SentimentRepository",
    "SentimentService",
]
