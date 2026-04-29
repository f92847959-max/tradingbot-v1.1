from sentiment.sentiment_aggregator import SentimentAggregator


def test_ewm_1h(sample_articles, reference_now):
    features = SentimentAggregator(halflife_minutes=30).get_features_at(reference_now, sample_articles)

    assert features["sent_1h"] > 0.0
    assert features["news_count_1h"] == 2.0


def test_ewm_4h(sample_articles, reference_now):
    features = SentimentAggregator(halflife_minutes=30).get_features_at(reference_now, sample_articles)

    assert -1.0 <= features["sent_4h"] <= 1.0
    assert features["sent_4h"] != features["sent_1h"]


def test_ewm_24h(sample_articles, reference_now):
    features = SentimentAggregator(halflife_minutes=30).get_features_at(reference_now, sample_articles)

    assert -1.0 <= features["sent_24h"] <= 1.0
    assert features["sent_24h"] != 0.0


def test_momentum(sample_articles, reference_now):
    features = SentimentAggregator(halflife_minutes=30).get_features_at(reference_now, sample_articles)

    assert features["sent_momentum"] == features["sent_1h"] - features["sent_4h"]


def test_divergence_placeholder(sample_articles, reference_now):
    features = SentimentAggregator().get_features_at(reference_now, sample_articles)

    assert "sent_divergence" not in features


def test_empty_data_returns_zero(reference_now):
    features = SentimentAggregator().get_features_at(reference_now, [])

    assert features == {
        "sent_1h": 0.0,
        "sent_4h": 0.0,
        "sent_24h": 0.0,
        "sent_momentum": 0.0,
        "news_count_1h": 0.0,
    }
