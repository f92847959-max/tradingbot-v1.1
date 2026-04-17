"""RED tests for SENT-01 -- filled in by Plan 11-02."""
import pytest


def test_filter_gold_relevant_articles(sample_feed_bytes):
    pytest.fail("Wave 0 red test -- feed filter impl in Plan 11-02")


def test_keyword_match_min_threshold(sample_feed_bytes):
    pytest.fail("Wave 0 red test -- keyword threshold impl in Plan 11-02")


def test_etag_caching_returns_304(sample_feed_bytes):
    pytest.fail("Wave 0 red test -- ETag handling impl in Plan 11-02")


def test_url_normalization_strips_utm(sample_feed_bytes):
    pytest.fail("Wave 0 red test -- URL normalization impl in Plan 11-02")
