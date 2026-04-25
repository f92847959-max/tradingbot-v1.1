---
phase: 13-orderbuch-analyse
plan: 01
subsystem: ai_engine.features
tags: [orderflow, features, ohlcv, delta]
requirements: [FLOW-01, FLOW-02, FLOW-03]
key_files:
  created:
    - ai_engine/features/orderflow_features.py
    - tests/test_orderflow_features.py
tests:
  command: "python -m pytest tests/test_orderflow_features.py -q"
  result: "9 passed"
completed: "2026-04-25T21:51:13.220Z"
---

# Phase 13 Plan 01 Summary: Order-Flow Feature Core

Added the OHLCV-derived `OrderFlowFeatures` feature family.

One-liner: `OrderFlowFeatures` creates finite, leakage-aware `flow_*` features for delta, cumulative delta, divergence, volume profile distances, liquidity zones, fair value gaps, absorption, volume z-score, and optional L1 imbalance fallback.

## What Changed

- Added `ai_engine/features/orderflow_features.py` with BVC-style delta, rolling profile levels, liquidity-zone distances, closed-candle FVG distances, and absorption scoring.
- Kept the implementation dependency-free beyond existing numpy/pandas utilities and avoided hard dependency on `smartmoneyconcepts`.
- Added focused unit tests for feature names, NaN/inf safety, delta direction, doji safety, profile warm-up, liquidity/absorption features, optional L1 defaults, clipping, and future-row mutation safety.

## Verification

- `python -m pytest tests/test_orderflow_features.py -q` -> `9 passed`
