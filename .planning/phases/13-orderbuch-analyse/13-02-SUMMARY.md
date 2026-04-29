---
phase: 13-orderbuch-analyse
plan: 02
subsystem: market_data
tags: [orderflow, quote-flow, capital-com, settings]
requirements: [FLOW-01, FLOW-04]
key_files:
  created:
    - market_data/orderflow_stream.py
    - tests/test_orderflow_stream.py
  modified:
    - config/settings.py
tests:
  command: "python -m pytest tests/test_orderflow_stream.py tests/test_orderflow_features.py -q"
  result: "16 passed"
completed: "2026-04-25T21:53:37.301Z"
---

# Phase 13 Plan 02 Summary: Quote-Flow Enrichment

Added optional Capital.com L1 quote-flow enrichment.

One-liner: `QuoteFlowAggregator` converts available Capital.com quote payloads into candle-aligned `flow_l1_imbalance` features while neutralizing missing quantities and avoiding any true Level-2/DOM claim.

## What Changed

- Added `market_data/orderflow_stream.py` with quote payload normalization, bounded L1 imbalance calculation, and timeframe bucket aggregation.
- Added disabled-by-default order-flow settings for feature windows and quote enrichment.
- Added tests for signed imbalance, missing/invalid fallback, Capital.com payload shape, invalid payload rejection, candle bucketing, and default settings.

## Verification

- Initial run exposed two parser bugs: missing quantities were treated as pressure and invalid prices were accepted as `0.0`.
- Fixed parser behavior so missing quantities are neutral and invalid bid/offer prices reject the payload.
- `python -m pytest tests/test_orderflow_stream.py tests/test_orderflow_features.py -q` -> `16 passed`
