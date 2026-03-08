---
phase: "04"
plan: "01"
subsystem: strategy
tags: [regime-detection, market-classification, adx, atr]
dependency_graph:
  requires: [market_data/indicators.py]
  provides: [strategy/regime_detector.py, strategy/regime_params.py]
  affects: []
tech_stack:
  added: []
  patterns: [enum-based-classification, hysteresis-state-machine, vectorized-series]
key_files:
  created:
    - strategy/regime_detector.py
    - strategy/regime_params.py
    - tests/test_regime_detector.py
  modified:
    - shared/constants.py
decisions:
  - "ADX + ATR ratio sufficient for 3-state classification (BB width excluded per plan)"
  - "Hysteresis counter initialized to 0 (not 1) to require exactly min_confirm_candles transitions"
  - "RANGING is the safest default for all fallback/error cases"
metrics:
  duration: "413s"
  completed: "2026-03-08T12:40:50Z"
  tasks_completed: 5
  tests_added: 33
  tests_total: 259
  regressions: 0
requirements:
  - STRAT-03
---

# Phase 4 Plan 01: Regime Detection Foundation Summary

Rule-based market regime classifier using ADX thresholds and ATR ratio with hysteresis for live trading and stateless vectorized series for backtesting.

## What Was Built

### strategy/regime_detector.py
- **MarketRegime** enum: TRENDING, RANGING, VOLATILE
- **RegimeState** dataclass: regime, adx, atr, atr_ratio, confidence (0-1)
- **RegimeDetector** class with configurable thresholds from shared constants
  - `detect(df)` -- stateful with hysteresis for live trading; tracks `_current_regime` and `_confirm_count` to prevent flickering
  - `detect_series(df)` -- stateless vectorized classification for backtesting/training; no hysteresis
  - `_classify_single()` -- core priority-based logic: VOLATILE > TRENDING > RANGING > ambiguous tiebreak
  - Handles both `adx` and `adx_14` column names
  - NaN ATR gracefully returns RANGING with confidence 0.0

### strategy/regime_params.py
- **REGIME_PARAMS** dict mapping each MarketRegime to strategy parameters:
  - TRENDING: wider TP (2.5x ATR), standard SL (1.5x), lower confidence bar (0.65)
  - RANGING: tight TP/SL (1.5x/1.0x), higher bar (0.75), lower R:R minimum (1.2)
  - VOLATILE: widest TP/SL (3.0x/2.0x), highest bar (0.80)
- **get_regime_params()** with RANGING fallback for unknown regimes

### shared/constants.py
- Added 5 regime detection defaults: ADX_TREND_THRESHOLD (25.0), ADX_RANGE_THRESHOLD (20.0), ATR_VOLATILE_RATIO (1.5), REGIME_LOOKBACK_PERIODS (20), REGIME_MIN_CONFIRM_CANDLES (3)

### tests/test_regime_detector.py
- 33 tests across 12 test classes covering:
  - TRENDING/RANGING/VOLATILE detection with confidence checks
  - Ambiguous ADX zone tiebreak by ATR ratio
  - NaN ATR and empty DataFrame edge cases
  - detect_series vectorized output (length, types, adx_14 fallback)
  - Hysteresis: flicker rejection, confirmed switch, counter reset
  - Regime params: key completeness, numeric values, relative ordering
  - MarketRegime enum membership and RegimeState dataclass fields

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Hysteresis counter initialization**
- **Found during:** Task 4 (test writing)
- **Issue:** `_confirm_count` was initialized to 1 on first detection, causing regime switches to happen after `min_confirm_candles - 1` detections instead of the full count
- **Fix:** Changed initial `_confirm_count` from 1 to 0
- **Files modified:** strategy/regime_detector.py
- **Commit:** 3e0070a

**2. [Rule 1 - Bug] Volatile series test data calibration**
- **Found during:** Task 4 (test writing)
- **Issue:** ATR spike of 2.0 over base 1.0 was insufficient to maintain ratio > 1.5 after 10 rows of rolling average adjustment
- **Fix:** Increased spike to 3.0 over 5 rows and tested index 25 (first spike row)
- **Files modified:** tests/test_regime_detector.py
- **Commit:** 3e0070a

## Commits

| Hash    | Type  | Description                                          |
|---------|-------|------------------------------------------------------|
| 22b6ff3 | chore | Add regime detection defaults to shared constants    |
| 6ec1f98 | feat  | Create RegimeDetector with MarketRegime and RegimeState |
| e40215c | feat  | Create regime parameter lookup table                 |
| 3e0070a | test  | Add 33 tests and fix hysteresis init bug             |

## Test Results

- **New tests:** 33 passed
- **Full suite:** 259 passed, 9 failed (all pre-existing), 8 collection errors (all pre-existing)
- **Regressions:** 0

## Self-Check: PASSED

All 4 created/modified files verified on disk. All 4 commit hashes verified in git log.
