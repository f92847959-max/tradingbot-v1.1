"""RED tests for SENT-03 -- filled in by Plan 11-02."""
import pytest


def test_ewm_1h(sample_articles, reference_now):
    pytest.fail("Wave 0 red test -- EWM 1h window in Plan 11-02")


def test_ewm_4h(sample_articles, reference_now):
    pytest.fail("Wave 0 red test -- EWM 4h window in Plan 11-02")


def test_ewm_24h(sample_articles, reference_now):
    pytest.fail("Wave 0 red test -- EWM 24h window in Plan 11-02")


def test_momentum(sample_articles, reference_now):
    pytest.fail("Wave 0 red test -- momentum = sent_1h - sent_4h in Plan 11-02")


def test_divergence_placeholder():
    pytest.fail("Wave 0 red test -- divergence requires price_direction input in Plan 11-03")


def test_empty_data_returns_zero(reference_now):
    pytest.fail("Wave 0 red test -- empty fallback in Plan 11-02")
