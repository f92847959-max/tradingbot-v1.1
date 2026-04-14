---
status: partial
phase: 09-advanced-risk-position-sizing
source: [09-VERIFICATION.md]
started: "2026-04-14"
updated: "2026-04-14"
---

## Current Test

[awaiting human testing]

## Tests

### 1. Portfolio Heat Decrement in Demo Session
expected: Run bot in demo, open trades, let SL/TP close them — logs show heat released via `on_position_closed` and new trades are not blocked by accumulated heat
result: [pending]

### 2. Kelly Fraction Loading at Startup
expected: Start with >30 DB trades — logs show "Kelly updated: mode=half, f*=..." rather than "fixed_fractional" reasoning in approve_trade sizing
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
