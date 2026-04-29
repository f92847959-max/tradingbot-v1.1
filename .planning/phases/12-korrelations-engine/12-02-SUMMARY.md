---
phase: 12
plan: 02
subsystem: correlation
tags: [correlation, calculator, divergence, regime, lead-lag]
requirements: [CORR-02, CORR-03]
dependency-graph:
  requires:
    - "12-01: AssetFetcher.fetch_daily_closes() DataFrame contract"
    - "correlation.snapshot.CorrelationSnapshot"
  provides:
    - "correlation.correlation_calculator.compute_snapshot(closes)"
    - "rolling_corr(a, b, window)"
    - "divergence_score(a, b, lookback)"
    - "lead_lag(a, b, max_lag)"
    - "regime(current_corr, recent_corrs)"
  affects:
    - "correlation/__init__.py exports compute_snapshot"
key-files:
  created:
    - "correlation/correlation_calculator.py"
    - "tests/test_correlation_calculator.py"
  modified:
    - "correlation/__init__.py"
decisions:
  - "Correlation calculation stays pure: no yfinance calls, no file I/O, deterministic DataFrame-to-snapshot transform."
  - "Missing assets and insufficient windows return neutral 0.0 values instead of NaN or exceptions."
  - "Lead-lag sign convention: negative means gold leads the compared asset; positive means the compared asset leads gold."
metrics:
  tests_added: 5
  verification_command: "python -m pytest tests\\test_asset_fetcher.py tests\\test_correlation_calculator.py tests\\test_correlation_features.py tests\\test_orderflow_integration.py -q"
  verification_result: "21 passed, 2 warnings"
  completed: "2026-04-29"
---

# Phase 12 Plan 02: Correlation Calculator Summary

Plan 12-02 completed the mathematical core for the correlation engine. The implementation turns aligned daily close data into a 20-field `CorrelationSnapshot` using rolling Pearson correlations, divergence scoring, regime classification, and lead-lag cross-correlation.

## Files

### Created
- `correlation/correlation_calculator.py` - Pure helper functions plus `compute_snapshot(closes: pd.DataFrame) -> CorrelationSnapshot`.
- `tests/test_correlation_calculator.py` - Unit coverage for rolling correlation, insufficient data fallback, regime detection, divergence scoring, and lead-lag direction.

### Modified
- `correlation/__init__.py` - Exports `compute_snapshot` while keeping `AssetFetcher` as a lazy optional dependency.

## Verification

- `python -m compileall correlation ai_engine\features\correlation_features.py ai_engine\features\feature_engineer.py tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py` - passed.
- `python -m pytest tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py tests\test_orderflow_integration.py -q` - 21 passed, 2 warnings.

The warnings are external Python 3.14 deprecation warnings from `google._upb._message` during optional dependency import; no Phase 12 behavior failed.

## Acceptance

- CORR-02 is satisfied by rolling 20/60/120 correlation values for DXY, US10Y, silver, VIX, and S&P 500 against gold.
- CORR-03 is satisfied by divergence scores, regime classification, and lead-lag scores.
- Missing or short input data degrades to bounded neutral values instead of NaN.

## Handoff to Plan 12-03

`compute_snapshot(closes)` now provides the stable `CorrelationSnapshot` contract consumed by the ML feature pipeline.
