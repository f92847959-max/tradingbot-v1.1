---
phase: 12
plan: 03
subsystem: feature-engineering
tags: [correlation, feature-engineer, ml-features, graceful-fallback]
requirements: [CORR-04]
dependency-graph:
  requires:
    - "12-02: CorrelationSnapshot from compute_snapshot"
  provides:
    - "ai_engine.features.correlation_features.CorrelationFeatures"
    - "FeatureEngineer.create_features(..., correlation_snapshot=...)"
    - "FeatureEngineer.get_feature_groups()['correlation']"
  affects:
    - "ai_engine/features/feature_engineer.py"
key-files:
  created:
    - "ai_engine/features/correlation_features.py"
    - "tests/test_correlation_features.py"
  modified:
    - "ai_engine/features/feature_engineer.py"
decisions:
  - "Correlation features are always part of the base feature group so model schemas stay stable."
  - "A missing snapshot broadcasts all 20 correlation columns as 0.0 for startup/backtest fallback."
  - "Feature cache is bypassed when a non-null correlation snapshot is supplied to prevent stale correlation columns."
metrics:
  tests_added: 4
  verification_command: "python -m pytest tests\\test_asset_fetcher.py tests\\test_correlation_calculator.py tests\\test_correlation_features.py tests\\test_orderflow_integration.py -q"
  verification_result: "21 passed, 2 warnings"
  completed: "2026-04-29"
---

# Phase 12 Plan 03: Correlation Feature Integration Summary

Plan 12-03 wired the correlation snapshot into the ML feature pipeline. `CorrelationFeatures` broadcasts the 20 snapshot values into every feature row, and `FeatureEngineer` exposes the group through its normal feature-name and feature-group APIs.

## Files

### Created
- `ai_engine/features/correlation_features.py` - Broadcasts `CorrelationSnapshot` values into DataFrame columns and exposes stable feature names.
- `tests/test_correlation_features.py` - Covers feature-name count, no-snapshot fallback, FeatureEngineer group registration, and no-NaN/no-out-of-range output.

### Modified
- `ai_engine/features/feature_engineer.py` - Adds correlation features to the base pipeline and accepts `correlation_snapshot`.

## Verification

- `python -m compileall correlation ai_engine\features\correlation_features.py ai_engine\features\feature_engineer.py tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py` - passed.
- `python -m pytest tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py tests\test_orderflow_integration.py -q` - 21 passed, 2 warnings.

The warnings are external Python 3.14 deprecation warnings from `google._upb._message` during optional dependency import; no Phase 12 behavior failed.

## Acceptance

- CORR-04 is satisfied: the ML feature matrix contains all 20 correlation columns.
- `FeatureEngineer.get_feature_groups()` includes `correlation`.
- Missing snapshots produce zero-valued columns, never NaN.
- Correlation values stay bounded in the expected `[-1, 1]` range for tested generated snapshots.

## Phase Result

Phase 12 is complete end to end:

- 12-01 provides market asset fetching and the 20-field snapshot model.
- 12-02 computes deterministic correlation snapshots.
- 12-03 exposes those snapshots as first-class ML features.
