---
phase: "02-training-pipeline-walk-forward-validation"
plan: "01"
subsystem: "ai_engine/training"
tags: [walk-forward, validation, data-quality, expanding-windows]
dependency_graph:
  requires: []
  provides: [WalkForwardValidator, WindowSpec, validate_minimum_duration]
  affects: [pipeline.py, data_preparation.py]
tech_stack:
  added: []
  patterns: [expanding-window-walk-forward, per-window-scaler-fitting]
key_files:
  created:
    - ai_engine/training/walk_forward.py
    - tests/test_walk_forward.py
  modified:
    - ai_engine/training/pipeline.py
    - ai_engine/training/data_preparation.py
decisions:
  - "Expanding (anchored) windows with train_start=0 for all windows"
  - "Dynamic window count based on data size (9 windows for 12000 samples)"
  - "Test period = 20% of total window size (25% of train)"
  - "min_train_samples=1500, min_test_samples=200"
  - "Per-window fresh FeatureScaler to prevent data leakage"
  - "85/15 internal split within training portion for val/early-stopping"
metrics:
  duration_seconds: 264
  completed: "2026-03-06T20:13:41Z"
  tasks_completed: 4
  tasks_total: 4
  tests_added: 17
  tests_passed: 17
---

# Phase 2 Plan 1: Walk-Forward Validation Engine + Data Validation Summary

Walk-forward validation with expanding windows replacing single 70/15/15 split, plus 6-month minimum data check.

## Tasks Completed

| Task | Description | Commit | Key Files |
|------|-------------|--------|-----------|
| 1 | Create WalkForwardValidator class | `e728126` | `ai_engine/training/walk_forward.py` |
| 2 | Add 6-month data validation | `8b2e056` | `ai_engine/training/data_preparation.py` |
| 3 | Refactor pipeline.py for walk-forward | `77de0c2` | `ai_engine/training/pipeline.py` |
| 4 | Create test suite | `7666c1a` | `tests/test_walk_forward.py` |

## Implementation Details

### walk_forward.py (new, 310 lines)

- `WindowSpec` dataclass with train/test index boundaries and size properties
- `calculate_walk_forward_windows()` function: dynamic window count, expanding anchored design, 20% test ratio, respects purge gap and min sample sizes
- `WalkForwardValidator` class with `calculate_windows()`, `run_window()`, and `run_all_windows()` methods
- `run_window()` creates fresh `FeatureScaler` per window (TRAIN-02 compliance), trains XGBoost + LightGBM, runs feature selection, tunes trade filters, evaluates on test portion
- Reuses existing components: `ModelEvaluator`, `tune_trade_filter`, `FeatureScaler`, model `.train()` methods

### pipeline.py (refactored, 206 lines)

- Steps 1-5 unchanged: validate, features, labels, warmup, split X/y
- Steps 6-12 replaced by step 6 (walk-forward) + step 7 (save)
- 6-month data validation added at step 1 (TRAIN-07)
- Dynamic purge gap computed once, passed to WalkForwardValidator
- Backward-compatible results dict: last window populates existing keys
- Metadata extended with `walk_forward` section containing per-window summaries

### data_preparation.py (extended)

- `validate_minimum_duration()` method: checks DatetimeIndex span, raises ValueError if < min_months

### Window behavior with 12000 samples

9 expanding windows generated, train_start always 0, test periods non-overlapping, purge gap = 60 candles between train_end and test_start. Test sizes grow proportionally from 375 to 2012 samples.

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **Window count algorithm**: Start at min_train_samples (1500), compute test_size = max(train_end * 0.25, 200), advance train_end to test_end for next window
2. **Internal validation split**: 85% train / 15% val within each window's training portion (for early stopping and trade filter tuning)
3. **Feature selection**: Per-window using XGBoost importance with 0.5% threshold, re-train if features dropped

## Verification Results

- 17/17 pytest tests pass
- Manual verification: 9 windows generated from 12000 samples (>= 5 required)
- No regressions in existing test suite (43 related tests pass)

## Self-Check: PASSED

All 4 created/modified files exist on disk. All 4 commit hashes verified in git log.
