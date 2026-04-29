---
phase: 12
slug: korrelations-engine
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-18
completed: 2026-04-29
---

# Phase 12 - Validation Strategy

Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | pytest.ini / pyproject.toml |
| Quick run command | `pytest tests/test_correlation_features.py tests/test_correlation_calculator.py tests/test_asset_fetcher.py -x -q` |
| Full sampled command | `pytest tests/test_asset_fetcher.py tests/test_correlation_calculator.py tests/test_correlation_features.py tests/test_orderflow_integration.py -q` |
| Latest runtime | 3.07 seconds |

## Sampling Rate

- After every task commit: run targeted correlation tests.
- After every plan wave: run the sampled feature/orderflow regression set.
- Before verification: targeted correlation suite must be green.
- Max feedback latency: 30 seconds.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | CORR-01 | unit | `pytest tests/test_asset_fetcher.py -x -q` | present | green |
| 12-01-02 | 01 | 1 | CORR-01 | unit | `pytest tests/test_asset_fetcher.py::test_cache_ttl -x -q` | present | green |
| 12-02-01 | 02 | 2 | CORR-02 | unit | `pytest tests/test_correlation_calculator.py::test_rolling_corr -x -q` | present | green |
| 12-02-02 | 02 | 2 | CORR-02 | unit | `pytest tests/test_correlation_calculator.py::test_insufficient_data -x -q` | present | green |
| 12-02-03 | 02 | 2 | CORR-03 | unit | `pytest tests/test_correlation_calculator.py::test_regime_detection -x -q` | present | green |
| 12-02-04 | 02 | 2 | CORR-03 | unit | `pytest tests/test_correlation_calculator.py::test_divergence_score -x -q` | present | green |
| 12-03-01 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_feature_names -x -q` | present | green |
| 12-03-02 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_none_snapshot -x -q` | present | green |
| 12-03-03 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_feature_engineer_group -x -q` | present | green |
| 12-03-04 | 03 | 3 | CORR-04 | unit | `pytest tests/test_correlation_features.py::test_no_nan -x -q` | present | green |

## Wave 0 Requirements

- [x] `tests/test_asset_fetcher.py` - covers CORR-01 with mocked yfinance and TTL cache.
- [x] `tests/test_correlation_calculator.py` - covers CORR-02 and CORR-03 with rolling correlation, regime, divergence, and lead-lag tests.
- [x] `tests/test_correlation_features.py` - covers CORR-04 feature names, graceful degradation, FeatureEngineer grouping, and no-NaN output.
- [x] `tests/conftest.py` - no extra correlation fixture required.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live yfinance fetch returns realistic data for DXY/US10Y/silver/VIX/SP500 | CORR-01 | External network and market-hours dependent | Run `python -m scripts.fetch_correlations_once` during US market hours and inspect the printed DataFrame. |
| Correlation-regime reporting in logs | CORR-03 | Requires live market stress to reproduce | Monitor logs over a trading week; breakdown z-score above 2.0 should emit a warning. |

## Validation Sign-Off

- [x] All tasks have automated verification or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency below 30 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** complete

## Automated Verification Evidence

- `python -m compileall correlation ai_engine\features\correlation_features.py ai_engine\features\feature_engineer.py tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py` - passed.
- `python -m pytest tests\test_asset_fetcher.py tests\test_correlation_calculator.py tests\test_correlation_features.py tests\test_orderflow_integration.py -q` - 21 passed, 2 warnings.
