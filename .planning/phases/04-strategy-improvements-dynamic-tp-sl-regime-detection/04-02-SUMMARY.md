---
phase: "04"
plan: "02"
subsystem: "ai_engine/training"
tags: [atr, dynamic-tp-sl, label-generation, backtester, training-alignment]
dependency_graph:
  requires: []
  provides: [dynamic-atr-labels, atr-backtester, atr-cli-args]
  affects: [label_generator, backtester, trainer, walk_forward, train_models]
tech_stack:
  added: []
  patterns: [per-candle-atr-distances, dynamic-vs-fixed-mode-branching]
key_files:
  created:
    - tests/test_dynamic_labels.py
  modified:
    - ai_engine/training/label_generator.py
    - ai_engine/training/backtester.py
    - ai_engine/training/trainer.py
    - ai_engine/training/walk_forward.py
    - scripts/train_models.py
    - tests/test_walk_forward_e2e.py
decisions:
  - "LabelGenerator defaults use_dynamic_atr=False for backward compat; ModelTrainer defaults True"
  - "Keep _vectorized_labeling and _vectorized_labeling_dynamic separate (scalar vs array performance)"
  - "Suppress RuntimeWarning on all-NaN nanmedian (handled by fallback logic)"
metrics:
  duration_seconds: 526
  completed_date: "2026-03-08T12:43:06Z"
  tasks_completed: 7
  tests_added: 18
  files_modified: 6
  files_created: 1
requirements:
  - STRAT-01
---

# Phase 4 Plan 02: Dynamic ATR-Based Labels and Backtester Alignment Summary

ATR-based dynamic TP/SL for label generation and backtesting, eliminating training-execution mismatch with live trading.

## What Was Done

### Task 1: LabelGenerator Dynamic ATR Mode (a2ee087)
- Added `use_dynamic_atr`, `tp_atr_multiplier`, `sl_atr_multiplier`, `min_tp_pips`, `min_sl_pips` params
- Created `_generate_dynamic_atr_labels()` computing per-candle TP/SL from ATR values
- Created `_vectorized_labeling_dynamic()` for per-candle array-based triple barrier labeling
- Refactored fixed path into `_generate_fixed_labels()` helper method
- NaN ATR handling: median fill for partial NaN, full fallback to fixed for all-NaN
- Updated `get_params()` to include ATR params in dynamic mode

### Task 2: Backtester ATR-Based TP/SL (fdef14a)
- Added `atr_values`, `tp_atr_multiplier`, `sl_atr_multiplier` params to `run_simple()`
- Per-trade TP/SL computed from ATR at trade entry when `atr_values` provided
- Added `avg_tp_pips`/`avg_sl_pips` to `_generate_report()` for correct expectancy calculation

### Task 3: ModelTrainer ATR Forwarding (84fcbbc)
- Added `use_dynamic_atr` (default `True`), `tp_atr_multiplier`, `sl_atr_multiplier` to `__init__`
- Passes all ATR config to LabelGenerator constructor

### Task 4: Walk-Forward ATR Info (5b61312)
- Stores `use_dynamic_atr`, `tp_atr_multiplier`, `sl_atr_multiplier` in window result dict

### Task 5: CLI Args (6ad7349)
- Added `--dynamic-atr` (default), `--no-dynamic-atr`, `--tp-atr-mult`, `--sl-atr-mult` to CLI
- Passes args to ModelTrainer; shows ATR mode in training summary output

### Task 6: Tests (881f575)
- 18 test cases covering dynamic ATR labels, fixed mode backward compat, backtester ATR, trainer forwarding
- Tests for high/low ATR behavior, NaN handling, floor clamping, missing column error

### Task 7: E2E Test Fix (4d3344e)
- Updated e2e test to pass `use_dynamic_atr=False` since synthetic data has no `atr_14` column

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] E2E test regression from default change**
- **Found during:** Task 7 (full test suite verification)
- **Issue:** `ModelTrainer` now defaults to `use_dynamic_atr=True`, but the e2e test uses synthetic OHLCV data without an `atr_14` column, causing `ValueError`
- **Fix:** Added `use_dynamic_atr=False` to e2e test's `ModelTrainer` instantiation
- **Files modified:** `tests/test_walk_forward_e2e.py`
- **Commit:** 4d3344e

## Test Results

- New tests: 18/18 passing
- Full test suite: 260 passed, 8 failed (all pre-existing failures)
- Pre-existing failures (not caused by this plan):
  - 6 in `test_indicators.py` (looking for `atr` column, should be `atr_14`)
  - 1 in `test_risk_integration.py` (DB sync failure)
  - 1 in `test_risk_manager.py` (weekend trading hours rejection)
- 0 regressions from this plan's changes

## Commits

| Order | Hash    | Type     | Description                                            |
|-------|---------|----------|--------------------------------------------------------|
| 1     | a2ee087 | feat     | Add dynamic ATR-based label generation to LabelGenerator |
| 2     | fdef14a | feat     | Add ATR-based per-trade TP/SL to Backtester.run_simple() |
| 3     | 84fcbbc | feat     | Pass ATR params from ModelTrainer to LabelGenerator     |
| 4     | 5b61312 | feat     | Store ATR mode info in walk-forward window results      |
| 5     | 6ad7349 | feat     | Add dynamic ATR CLI args to train_models.py             |
| 6     | 881f575 | test     | Add 18 test cases for dynamic ATR labels and backtester |
| 7     | 4d3344e | fix      | Update e2e test to use fixed labels for synthetic data  |

## Self-Check: PASSED

- All 8 files verified present
- All 7 commits verified in git log
