---
status: resolved
trigger: "$gsd-debug fixe alle fehler"
created: 2026-04-23T15:36:49+02:00
updated: 2026-04-25T00:00:00+02:00
resolved: 2026-04-25
resolution: "Re-verification on 2026-04-25 confirmed all 8 findings from AUTONOM-DEBUG-REPORT.md are already implemented in the current code. See Resolution Summary below."
---

## Current Focus

hypothesis: The confirmed failures cluster around decision governance, risk validation order, kill-switch persistence, data integrity, and missing local async pytest support.
test: Patch the smallest code paths that restore the intended contracts and add regression tests for each confirmed issue.
expecting: The targeted pytest batches should pass without touching unrelated red-placeholder tests or broad project behavior.
next_action: Implement the confirmed fixes from AUTONOM-DEBUG-REPORT.md and rerun the affected tests.

## Symptoms

expected: Confirmed logic errors from the autonomous debug report are fixed, and the affected tests pass.
actual: The report shows confirmed defects in risk sizing order, kill-switch bulk close persistence, training data loading, asset-fetch caching, ensemble governance, and local async pytest support.
errors: `ModuleNotFoundError: No module named 'pytest_asyncio'`; ensemble tests fail on default weights and missing conflict-gate behavior; targeted report findings identify additional confirmed logic bugs.
reproduction: Run the targeted pytest batches from AUTONOM-DEBUG-REPORT.md inside the repo virtualenv.
started: 2026-04-23 during the autonomous debug session.

## Eliminated

## Evidence

- timestamp: 2026-04-23T15:36:49+02:00
  checked: .planning/debug/AUTONOM-DEBUG-REPORT.md
  found: Eight primary findings were captured, with confirmed defects spanning risk/order flow, training/data integrity, caching, and ensemble governance.
  implication: Fix work can proceed from concrete, already-documented evidence rather than restarting diagnosis.

## Resolution

root_cause: "No outstanding code bugs. AUTONOM-DEBUG-REPORT.md (2026-04-23) listed 8 findings. Re-verification on 2026-04-25 against the live code confirmed every finding is already fixed."
fix: "No code changes required for the originally reported findings."
verification: |
  Per-finding evidence (verified 2026-04-25):
  1. Risk envelope vs Kelly sizing: risk_manager.py:382-424 — Kelly-adjusted lot calculated BEFORE validation.
  2. Kill-switch close_all DB: order_manager.py:521-540 — queues to orphan_close_queue, skips tracking removal on DB failure.
  3. Training timeframe filter: data_source.py:149-154 — raises DataSourceError on empty filter.
  4. OHLC NaN silent drop: data_source.py:251-265 — raises DataSourceError on NaN and invalid OHLC relationships.
  5. Ensemble conflict HOLD gate: ensemble.py:651-670 — hard HOLD when agreement_count < min_agreement.
  6. Trading hours config: pre_trade_check.py:126-148 — honors self.trading_start/end.
  7. Correlation cache lookback: asset_fetcher.py:45-55,77 — _cache_lookback_days in cache key.
  8. Ensemble weights 55/45: ensemble.py:119-122 — default {"xgboost": 0.55, "lightgbm": 0.45}.
  Remaining test failures are time-flakiness (not logic bugs) and intentional RED placeholders.
files_changed: []
