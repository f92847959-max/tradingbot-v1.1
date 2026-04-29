from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.features.sentiment_features import SentimentFeatures


class CountingAggregator:
    def __init__(self) -> None:
        self.calls = 0

    def get_features_at(self, now, window_records=None):
        self.calls += 1
        return {
            "sent_1h": 0.2,
            "sent_4h": 0.1,
            "sent_24h": 0.05,
            "sent_momentum": 0.1,
            "news_count_1h": 1.0,
        }


def test_feature_engineer_includes_sent_names():
    engineer = FeatureEngineer(sentiment_enabled=True)

    assert all(name in engineer.get_feature_names() for name in SentimentFeatures.FEATURE_NAMES)


def test_feature_engineer_disabled_adds_zero_columns(sample_candles_with_indicators):
    engineer = FeatureEngineer(sentiment_enabled=True, sentiment_aggregator=None)
    result = engineer.create_features(sample_candles_with_indicators.copy())

    assert (result[SentimentFeatures.FEATURE_NAMES] == 0.0).all().all()


def test_feature_engineer_bypasses_cache_for_sentiment(sample_candles_with_indicators):
    aggregator = CountingAggregator()
    engineer = FeatureEngineer(sentiment_enabled=True, sentiment_aggregator=aggregator)

    engineer.create_features(sample_candles_with_indicators.copy())
    engineer.create_features(sample_candles_with_indicators.copy())

    assert aggregator.calls == 2
