"""RED tests for SENT-04 integration -- filled in by Plan 11-03."""
import pytest


def test_feature_engineer_includes_sent_names():
    pytest.fail("Wave 0 red test -- FeatureEngineer exposes sent_* names in Plan 11-03")


def test_feature_engineer_disabled_adds_zero_columns():
    pytest.fail("Wave 0 red test -- sentiment_enabled=False -> 0.0 columns in Plan 11-03")


def test_feature_engineer_bypasses_cache_for_sentiment():
    pytest.fail("Wave 0 red test -- SentimentFeatures always called fresh in Plan 11-03")
