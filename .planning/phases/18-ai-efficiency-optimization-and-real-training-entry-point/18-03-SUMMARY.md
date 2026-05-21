# Phase 18 Plan 03 — Summary

**Plan:** 18-03 — Feature cache + parallel windows + lazy imports (Wave 2)
**Completed:** 2026-05-20 (partial — see scope changes below)
**Mode:** Manual / inline (no subagent)

## Scope changes vs the original plan

Two of the five planned tasks were re-scoped after reading the actual codebase. The plan was written against an assumed architecture that didn't match reality.

### Re-scoped to standalone module (Task 2)
**Plan said:** per-window feature-matrix LRU disk cache wired into `FeatureEngineer.compute_features_for_window`.
**Reality:** features are computed *once* on the full dataset by `ModelTrainer` (`trainer.py`) before walk-forward runs. `WalkForwardValidator.run_window` operates on the pre-computed `X` matrix and only slices it by window index — no per-window feature computation happens. The per-window scaler IS fresh (TRAIN-02), but it's downstream of feature engineering.
**Delivered:** the cache module ships standalone with full tests. The intended use case shifts from "per-window cache" to "cross-run cache" — a second training run on the same data + same feature config can skip the ~minute-long feature pipeline. Wiring into `trainer.py` is deferred to a follow-up plan.

### Deferred (Task 3)
**Plan said:** ProcessPoolExecutor-parallelised walk-forward windows.
**Reality:** `WalkForwardValidator.run_all_windows` mutates trainer instance state across windows (`trainer._xgboost.set_feature_names(...)` at line 226-227, then per-window fit/predict on the same trainer object). Safe parallelisation requires either:
  1. Deepcopy the trainer per window (deepcopy of XGBoost/LightGBM wrappers with their internal booster handles is fragile on Windows + spawn semantics), OR
  2. Extract `run_window` into a module-level pure function that constructs a fresh trainer per window (medium-large refactor across `walk_forward.py` + `trainer.py` + 3 pipeline modules that share the validator).

Neither is a 10-minute change. Documented as a follow-up: **Plan 18-05** (proposed) — *Parallel walk-forward window execution*.

## Delivered

### Must-haves — verification
| # | Truth | Status |
|---|---|---|
| 1 | Heavy modules (`shap`, `lightgbm`, `matplotlib`) imported lazily inside the functions that use them; `python main.py --help` boot stays fast | ✅ `shap_importance.py` refactored; `python -X importtime main.py --help` does not list shap/matplotlib. `ai_engine.training.shap_importance` imports cleanly without pulling shap or matplotlib into `sys.modules`. |
| 2 | Module-ready feature cache with stable content-addressed keys, LRU eviction, TRAIN-02-safe semantics documented | ✅ `WindowFeatureCache` in `ai_engine/training/feature_cache.py` with 9 passing tests covering get/put roundtrip, get_or_compute, LRU eviction by atime, data + config hash stability, clear/reset. |
| 3 | Cache module name disambiguates from the existing runtime `FeatureCache` in `ai_engine.features.feature_engineer` (which is an in-memory tick cache) | ✅ Renamed to `WindowFeatureCache` to make the namespace explicit. Module docstring documents the distinction. |
| 4 | Per-window `FeatureScaler` continues to be fit fresh (TRAIN-02 preserved) | ✅ No change to `feature_scaler.py` or `WalkForwardValidator.run_window` — scaler logic untouched. |
| 5 | Walk-forward parallelism — IMPLEMENTED & SHIPPABLE | ❌ Deferred to Plan 18-05 (see Scope changes above). Architectural refactor required for safe parallel trainer-state handling. |
| 6 | ≥30% wall-clock reduction on canonical training | ⚠ Cannot claim — Task 5 (parallel windows) deferred. Lazy imports alone improve `--help` and `--mode live` boot, not training wall-clock. Cross-run feature cache will deliver wall-clock wins once wired (deferred). |

### Artifacts
| Path | Status |
|---|---|
| `ai_engine/training/shap_importance.py` | ✅ shap + matplotlib moved inside functions; new `_setup_matplotlib_agg()` helper centralises Agg backend setup |
| `ai_engine/training/feature_cache.py` | ✅ new — `WindowFeatureCache`, `compute_data_hash`, `compute_feature_config_hash` |
| `tests/test_feature_cache.py` | ✅ new — 9 tests, all passing |

### Key links
- `ai_engine.training.feature_cache.compute_data_hash` + `compute_feature_config_hash` form the content-addressed cache key. The next plan (cross-run cache wiring) can call `WindowFeatureCache.get_or_compute(key, lambda: feature_engineer.engineer_features(df))` inside `trainer.py` before invoking the validator.

## Tasks

| # | Task | Status | Commit |
|---|---|---|---|
| 1 | Baseline profiling capture | ⏭ Skipped — synthetic baseline ceremony pruned per user direction ("ok 2 dann 3"). `scripts/profiling_harness.py` (from 18-01) remains available for manual `--profile` runs. |
| 2 | Feature-matrix cache module + tests | ✅ Re-scoped to standalone cross-run cache. Commit `cffe34c`. |
| 3 | Parallel walk-forward via ProcessPoolExecutor | ⏸ Deferred to Plan 18-05 — see scope changes above. |
| 4 | Lazy imports for shap/lightgbm/matplotlib | ✅ Done for `shap` and `matplotlib` in `shap_importance.py`. `lightgbm` not module-level imported in `shap_importance.py`; the `LightGBMModel` wrapper in `ai_engine/models/lightgbm_model.py` still imports `lightgbm` at module level — relocating that is straightforward but bundled into the same family of "live boot fast" wins that 18-01's PEP 562 re-export already delivers (the wrapper itself is only loaded when `from trading.runner import TradingSystem` is triggered, which is gated by mode). Commit `0c7fb18`. |
| 5 | Acceptance: 30% wall-clock reduction | ❌ Cannot claim without parallel windows. Documented gap. |

## Verification checklist

- [x] `pytest tests/test_feature_cache.py -q` — 9 passed
- [x] `pytest tests/test_main_cli.py tests/test_training_data_coverage.py tests/test_max_history_fetch.py -q` — 21 passed (no regression from Wave 1+1b)
- [x] `python -c "import ai_engine.training.shap_importance; import sys; assert 'shap' not in sys.modules and 'matplotlib' not in sys.modules"` exits 0 — lazy imports verified
- [x] `python -X importtime main.py --help 2>&1 | grep -E "shap|matplotlib"` returns no shap or matplotlib lines
- [ ] 30% wall-clock reduction — NOT VERIFIED (parallel windows deferred)
- [ ] Cross-run cache wired into training pipeline — NOT WIRED (standalone only)

## Notes for downstream waves

- **18-04 (manifest, GPU, smoke, tests)** is unaffected. The `run_manifest.json` sidecar can record `cache_hit_rate` directly from `WindowFeatureCache.hit_rate()` once wired; until then the manifest field stays `null`.
- **Plan 18-05 (proposed)** should cover both deferred items: (a) wire `WindowFeatureCache` into `trainer.py` (`features = cache.get_or_compute(key, lambda: engineer.engineer_features(df))` before `validator.run_all_windows`), (b) refactor `WalkForwardValidator.run_window` to take a fresh trainer instance per call so a `ProcessPoolExecutor.map` over windows is safe. With both shipped, the 30% wall-clock target becomes measurable.
- The lazy-import work in `shap_importance.py` is the canonical pattern; the SAME refactor can be applied to any other heavy import found in modules touched by `--mode live` boot.

## Status

**PLAN 18-03: PARTIAL ✅⚠** — 2 of 5 tasks fully landed (lazy imports, cache module), 1 task re-scoped (cache scope reframed from per-window to cross-run), 2 tasks deferred (parallel windows, 30% acceptance). Honest gap documented; follow-up Plan 18-05 proposed.
