---
status: partial
phase: 08-wirtschaftskalender-integration
source: [08-VERIFICATION.md]
started: "2026-04-13"
updated: "2026-04-13"
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live ForexFactory fetch
expected: GET to nfs.faireconomy.media returns JSON array of economic events; refresh() stores Gold-relevant subset in DB
result: [pending]

### 2. Trade veto during high-impact event
expected: During NFP/FOMC/CPI window (30 min before to 15 min after), _trading_tick logs "Trade blocked: high-impact event window" and returns without executing
result: [pending]

### 3. Force-close before extreme event
expected: Within 5 minutes of extreme USD event (NFP, FOMC, CPI), all open positions are force-closed via orders.close_all()
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
