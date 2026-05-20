# Phase 18 Plan 02 — Summary

**Plan:** 18-02 — 48-month production floor + `--max-history` cache-and-extend (Wave 1b)
**Completed:** 2026-05-20
**Mode:** Manual / inline (no subagent)

## Must-haves — verification

### Truths
| # | Truth | Status |
|---|---|---|
| 1 | Real training hard-errors when any selected timeframe has fewer than 48 months of usable history | ✅ `DataCoverageError` raised by `calculate_trainable_span(df, min_months=DEFAULT_MIN_MONTHS_PROD)` — test_47_months_raises_with_prod_floor passes |
| 2 | The 48-month floor is the new default for `--min-data-months` in start_ai_training.py and main.py train | ✅ `DEFAULT_MIN_DATA_MONTHS = 48`; `--help` shows `default: 48`; values below 48 are auto-raised with a WARNING |
| 3 | `--max-history` is a new opt-in flag that requests max history available and only fetches missing tails | ✅ `--max-history` flag on scripts/fetch_bulk_history.py; `fetch_with_cache()` returns without broker call when cache covers requested range (asserted by test) |
| 4 | Below-floor error message names the timeframe, the months observed, and the override flag | ✅ `calculate_trainable_span(timeframe_label=...)` embeds `timeframe=5m` + `--allow-short-data` hint in message |
| 5 | TRAIN-07 6-month legacy floor remains the floor for `--smoke` and unit tests only | ✅ `DEFAULT_MIN_MONTHS_SMOKE = 6` still works (test_smoke_floor_still_works passes) |

### Artifacts
| Path | Status |
|---|---|
| `ai_engine/training/data_coverage.py` | ✅ +constants (`DEFAULT_MIN_MONTHS_PROD`, `DEFAULT_MIN_MONTHS_SMOKE`), +timeframe_label kwarg, +`--allow-short-data` hint in messages |
| `start_ai_training.py` | ✅ `DEFAULT_MIN_DATA_MONTHS = 48`, `--allow-short-data` flag, auto-raise-with-warning when below floor |
| `scripts/fetch_bulk_history.py` | ✅ +`MAX_HISTORY_YEARS = 27`, +`--max-history` flag, +`compute_cached_range()`, +`fetch_with_cache()` |
| `tests/test_training_data_coverage.py` | ✅ +5 floor-enforcement tests (11 total, all passing) |
| `tests/test_max_history_fetch.py` | ✅ new, 4 tests on cache-and-extend (all passing) |

### Key links
- `start_ai_training.py` → `ai_engine.training.data_coverage.DEFAULT_MIN_MONTHS_PROD` (lazy import inside `run_train`) for the floor check.
- `scripts/fetch_bulk_history.fetch_with_cache` → existing `_fetch_timeframe_directly` chunk-skip logic — the cache-fully-covered short-circuit happens BEFORE `_import_dukascopy` is called.

## Tasks

| # | Task | Commit |
|---|---|---|
| 1+2 | RED tests + 48-month floor in `data_coverage.py` (combined for inline mode) | `f75a2fd` |
| 3 | Wire 48-month default + `--allow-short-data` into `start_ai_training.py` | `b72023d` |
| 4 | `--max-history` + cache-and-extend helpers in `scripts/fetch_bulk_history.py` + 4 tests | `42f4a54` |
| 5 | Regression-check via `main.py train --help` (no source change required) | this commit |

## Verification checklist

- [x] `pytest tests/test_training_data_coverage.py tests/test_max_history_fetch.py -q` exits 0 (15 passed in 0.16-0.20s)
- [x] `pytest tests/test_main_cli.py -q` still green (6 passed — no Wave-1 regression)
- [x] `python start_ai_training.py --help` shows `--min-data-months` default = 48 and includes `--allow-short-data`
- [x] `python scripts/fetch_bulk_history.py --help` includes `--max-history`
- [x] `python main.py train --help` includes `--allow-short-data` + `--min-data-months 48` (default)
- [x] Cached CSV in `data/` is NOT re-downloaded on a second `--max-history` invocation — proven by `test_fetch_with_cache_no_op_when_cache_covers_requested_range` (asserts both `_import_dukascopy` and `_fetch_timeframe_directly` mocks are NOT called)

## Notes for downstream waves

- **Floor enforcement in pipeline:** Wave 3 (Plan 18-03) does not need to re-implement the floor; `calculate_trainable_span` is already wired in start_ai_training and `scripts/train_models.py` reads the resolved `args.min_data_months`.
- **Walk-forward window scaling:** With the new 48-month floor and the existing `walk_forward.py` formula (min_train=1500, min_test=200, anchored, dynamic count), a 5m gold dataset yields ~36+ windows. This is the parallelism payoff target for 18-03 Task 3 (`ProcessPoolExecutor` over walk-forward windows).
- **`--max-history` consumer separation:** `--max-history` lives on `scripts/fetch_bulk_history.py` (the bulk-data tool), NOT on `main.py train` directly. Canonical real-training workflow:
  1. `python scripts/fetch_bulk_history.py --max-history --resample-from-base` (one-time / nightly)
  2. `python main.py train --use-csv-if-present --target core --timeframes 5m,15m,1h`
  Reasoning: the train surface stays focused on training; cache population is a separate concern handled by the bulk-fetch tool. Phase 18 D-13's "always-max-history" intent is satisfied by the operational workflow, not by collapsing two CLIs into one.
- **Phase 12.7 promotion gate:** untouched. Floor enforcement runs upstream in preflight (`calculate_trainable_span`), promotion logic continues to read its `production.json` / `promotion_artifact.json` schemas unchanged.

## Status

**PLAN 18-02: COMPLETE ✅** — ready for Wave 2 (Plan 18-03 — feature-matrix cache + parallel walk-forward + lazy imports).
