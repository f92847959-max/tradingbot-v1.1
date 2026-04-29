---
status: complete
phase: 09-advanced-risk-position-sizing
source: [09-VERIFICATION.md]
started: "2026-04-14"
updated: "2026-04-22T19:39:11.730Z"
---

## Current Test

[testing complete]

## Tests

### 1. Portfolio Heat Decrement in Demo Session
expected: Run bot in demo, open trades, let SL/TP close them — logs show heat released via `on_position_closed` and new trades are not blocked by accumulated heat
result: pass
evidence: Automated equivalent passed: `pytest tests/test_kelly_calculator.py tests/test_volatility_sizer.py tests/test_position_sizer_advanced.py tests/test_monte_carlo.py tests/test_portfolio_heat.py tests/test_equity_curve_filter.py tests/test_risk_integration_advanced.py -q` -> `111 passed`; includes `test_on_position_closed_reduces_heat`.

### 2. Kelly Fraction Loading at Startup
expected: Start with >30 DB trades — logs show "Kelly updated: mode=half, f*=..." rather than "fixed_fractional" reasoning in approve_trade sizing
result: pass
evidence: Automated equivalent passed: same Phase 9 test run -> `111 passed`; includes `test_update_trade_stats_changes_kelly_fraction` and status propagation for `kelly_fraction`.

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
