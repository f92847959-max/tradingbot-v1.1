---
phase: 05-backtesting-validation
plan: "02"
subsystem: backtesting
tags: [cli, e2e-test, backtest, walk-forward, uat]
dependency_graph:
  requires: ["05-01"]
  provides: ["BACK-01", "BACK-02", "BACK-03", "BACK-04"]
  affects: ["scripts/run_backtest.py", "tests/test_backtest_e2e.py"]
tech_stack:
  added: []
  patterns: ["argparse CLI", "pytest module-scoped fixture", "walk-forward OOS backtest"]
key_files:
  created:
    - scripts/run_backtest.py
    - tests/test_backtest_e2e.py
  modified: []
decisions:
  - "CLI defaults report output to {version_dir}/backtest_report.json for co-location with model files"
  - "E2E tests use use_dynamic_atr=False to control label generation deterministically in tests"
  - "Module-scoped pytest fixture trains model once (7000 candles) and shares across all 4 UAT tests for speed"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-25T15:51:31Z"
  tasks: 2
  files_created: 2
  files_modified: 0
---

# Phase 05 Plan 02: CLI Backtest Script and E2E Integration Test Summary

**One-liner:** CLI entry point for OOS backtesting (`run_backtest.py`) plus e2e test suite validating all 4 Phase 5 UAT criteria (BACK-01 through BACK-04).

## Changes Made

### Task 1: CLI Backtest Script (`scripts/run_backtest.py`)

Created `scripts/run_backtest.py` following the same CLI pattern as `scripts/train_models.py`:

- **Arguments:** `--version-dir` (required), `--csv`, `--broker`, `--synthetic`, `--count`, `--timeframe`, `--commission`, `--output`
- **Flow:**
  1. Validates `version_dir` contains `version.json` — exits with clear error if missing
  2. Loads data from CSV, broker (Capital.com via `fetch_broker_data`), or synthetic generator
  3. Computes features via `FeatureEngineer().create_features(df, timeframe)`
  4. Generates labels via `LabelGenerator` with params extracted from `version.json`
  5. Extracts `atr_14` column for dynamic ATR mode when `use_dynamic_atr=True`
  6. Removes 200-candle warmup period
  7. Separates X, y arrays from processed DataFrame
  8. Creates `BacktestRunner(version_dir, commission_per_trade_pips)` and calls `runner.run()`
  9. Prints formatted console report via `print_backtest_report(report, consistency)`
  10. Saves JSON report to `{version_dir}/backtest_report.json` (or `--output` path)

**Verification:** `python scripts/run_backtest.py --help` shows all 8 options correctly.

### Task 2: End-to-End Integration Test (`tests/test_backtest_e2e.py`)

Created `tests/test_backtest_e2e.py` with module-scoped fixture and 4 UAT tests:

- **Fixture `trained_version_dir`:** Generates 7000 synthetic candles (40min freq = >6 months), trains a `ModelTrainer` with `use_dynamic_atr=False`, returns `(version_dir, df)` — runs once per test session.

- **`test_back01_oos_validation` (BACK-01):** Creates `BacktestRunner` with trained version dir, runs on feature-engineered data, asserts `per_window_results` has 1+ windows and each window has `window_id` and `n_trades >= 0`.

- **`test_back02_realistic_costs` (BACK-02):** Runs two backtests — one with `commission=0.0`, one with `commission=50.0`. Asserts that if any trades occur, the high-commission run produces lower total pips (costs reduce profits).

- **`test_back03_report_metrics` (BACK-03):** Asserts report contains `aggregate` dict with `sharpe_ratio`, `profit_factor`, `win_rate`, `max_drawdown_pct`, `n_windows`; and `per_window` list where each entry has the same four metrics.

- **`test_back04_consistency` (BACK-04):** Asserts consistency dict contains `passes_60pct` (bool), `passes_20pct_dd` (bool), `overall_pass` (bool), `dd_violations` (int >= 0), `positive_pct` (float 0-1).

**All 4 tests pass in ~9 seconds on synthetic data.**

## Verification Results

```
python scripts/run_backtest.py --help    -- Shows all 8 CLI options correctly
pytest tests/test_backtest_e2e.py -v     -- 4/4 passed (9.18s)
pytest tests/ (phase-5-relevant tests)  -- 125/126 passed (1 pre-existing BB ordering failure)
```

## Deviations from Plan

None - plan executed exactly as written. Both files were already present and complete when execution began (created by a prior agent run). Verified correctness and committed atomically.

## Known Stubs

None - both files are fully functional with no stubs or placeholder data.

## Self-Check: PASSED

- `scripts/run_backtest.py`: FOUND
- `tests/test_backtest_e2e.py`: FOUND
- Commit `b4e16a4` (feat(05-02): create CLI backtest script): FOUND
- Commit `58eb561` (feat(05-02): add end-to-end integration test): FOUND
