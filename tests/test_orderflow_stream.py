"""Tests for optional Capital.com quote-flow enrichment."""

from __future__ import annotations

import pandas as pd

from config.settings import Settings
from market_data.orderflow_stream import (
    QuoteFlowAggregator,
    compute_l1_imbalance,
    normalize_quote_payload,
)


def test_l1_imbalance_is_bounded_and_signed() -> None:
    assert compute_l1_imbalance(3, 1) == 0.5
    assert compute_l1_imbalance(1, 3) == -0.5
    assert -0.01 < compute_l1_imbalance(4976, 5000) < 0.0


def test_l1_imbalance_missing_or_invalid_quantities_are_neutral() -> None:
    assert compute_l1_imbalance(None, 10) == 0.0
    assert compute_l1_imbalance(10, None) == 0.0
    assert compute_l1_imbalance(0, 0) == 0.0
    assert compute_l1_imbalance("bad", "data") == 0.0


def test_normalize_quote_payload_from_capital_shape() -> None:
    record = normalize_quote_payload(
        {
            "timestamp": 1_748_000_000_000,
            "bid": 2045.50,
            "ofr": 2045.53,
            "bidQty": 4976.0,
            "ofrQty": 5000.0,
        }
    )

    assert record is not None
    assert record.timestamp.tzinfo is not None
    assert record.bid == 2045.50
    assert record.ofr == 2045.53
    assert record.spread > 0.0
    assert -1.0 <= record.flow_l1_imbalance <= 1.0


def test_normalize_quote_payload_rejects_missing_price_or_timestamp() -> None:
    assert normalize_quote_payload({"bid": 2045.50, "ofr": 2045.53}) is None
    assert normalize_quote_payload({"timestamp": "2026-01-01T00:00:00Z", "bid": "bad"}) is None


def test_quote_aggregator_buckets_by_timeframe() -> None:
    aggregator = QuoteFlowAggregator(timeframe="5m")
    aggregator.add_payload(
        {
            "timestamp": "2026-02-23T08:00:05Z",
            "bid": 2045.50,
            "ofr": 2045.53,
            "bidQty": 3,
            "ofrQty": 1,
        }
    )
    aggregator.add_payload(
        {
            "timestamp": "2026-02-23T08:04:55Z",
            "bid": 2045.60,
            "ofr": 2045.64,
            "bidQty": 1,
            "ofrQty": 3,
        }
    )
    aggregator.add_payload(
        {
            "timestamp": "2026-02-23T08:05:00Z",
            "bid": 2045.70,
            "ofr": 2045.74,
            "bidQty": 4,
            "ofrQty": 1,
        }
    )

    frame = aggregator.to_frame()

    assert len(frame) == 2
    first_bucket = pd.Timestamp("2026-02-23T08:00:00Z")
    second_bucket = pd.Timestamp("2026-02-23T08:05:00Z")
    assert frame.loc[first_bucket, "quote_count"] == 2
    assert frame.loc[first_bucket, "flow_l1_imbalance"] == 0.0
    assert frame.loc[second_bucket, "flow_l1_imbalance"] == 0.6
    assert "flow_l1_imbalance_ema_10" in frame.columns


def test_quote_aggregator_ignores_invalid_payloads() -> None:
    aggregator = QuoteFlowAggregator(timeframe="5m")

    assert aggregator.add_payload({"bid": 1.0, "ofr": 1.1}) is None
    assert aggregator.to_frame().empty


def test_orderflow_settings_are_disabled_by_default() -> None:
    settings = Settings()

    assert settings.orderflow_enabled is False
    assert settings.orderflow_quote_enrichment_enabled is False
    assert settings.orderflow_profile_window == 200
    assert settings.orderflow_liquidity_window == 20
