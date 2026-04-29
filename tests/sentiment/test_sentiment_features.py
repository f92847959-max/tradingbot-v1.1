import pandas as pd

from ai_engine.features.sentiment_features import SentimentFeatures


class DummyAggregator:
    def get_features_at(self, now, window_records=None):
        return {
            "sent_1h": 0.75,
            "sent_4h": 0.25,
            "sent_24h": 0.1,
            "sent_momentum": 0.5,
            "news_count_1h": 3.0,
        }


def _df():
    return pd.DataFrame(
        {"close": [2000.0, 2001.0]},
        index=pd.date_range("2026-04-16T11:55:00Z", periods=2, freq="5min"),
    )


def test_feature_columns():
    result = SentimentFeatures(DummyAggregator()).calculate(_df())

    assert SentimentFeatures.FEATURE_NAMES == [
        "sent_1h",
        "sent_4h",
        "sent_24h",
        "sent_momentum",
        "sent_divergence",
        "news_count_1h",
    ]
    assert all(name in result.columns for name in SentimentFeatures.FEATURE_NAMES)


def test_feature_names_list():
    names = SentimentFeatures().get_feature_names()

    assert names == SentimentFeatures.FEATURE_NAMES
    assert names is not SentimentFeatures.FEATURE_NAMES


def test_disabled_aggregator_zero_fallback():
    result = SentimentFeatures(None).calculate(_df())

    assert (result[SentimentFeatures.FEATURE_NAMES] == 0.0).all().all()
