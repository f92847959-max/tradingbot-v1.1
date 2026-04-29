---
status: passed
phase: 10-smart-exit-engine
score: 5/5
requirements: [EXIT-01, EXIT-02, EXIT-03, EXIT-04, EXIT-05]
tests: 40 passed
verified: "2026-04-22T19:39:11.730Z"
---

# Phase 10 Verification: Smart Exit Engine

## Goal

Smart dynamic exit management for XAU/USD: dynamic SL, dynamic TP, ATR trailing, TP1 partial close, and early reversal exits.

## Must-Haves

1. Dynamic SL from ATR plus structure levels -- verified by `tests/test_exit_engine_core.py`.
2. Dynamic TP from Fibonacci/S/R with TP1 -- verified by `tests/test_exit_engine_core.py`.
3. Trailing stop activates after +1R and trails by ATR -- verified by `tests/test_exit_engine_management.py`.
4. Partial close emits a one-time 50% TP1 action -- verified by `tests/test_exit_engine_management.py`.
5. Exit signals detect reversal candles and momentum divergence -- verified by `tests/test_exit_engine_core.py`.

## Test Evidence

- `python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_management.py -q` -> `40 passed`.

## Notes

The new trailing and partial-close modules are pure decision logic. Broker execution remains isolated in `order_management/`; this keeps Phase 10 testable and avoids changing Capital.com order semantics without a dedicated broker-integration phase.
