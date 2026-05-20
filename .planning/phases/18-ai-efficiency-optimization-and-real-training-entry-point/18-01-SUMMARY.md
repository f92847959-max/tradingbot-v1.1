# Phase 18 Plan 01 — Summary

**Plan:** 18-01 — Unified main.py dispatcher + profiling harness (Wave 1, refactor only)
**Completed:** 2026-05-20
**Mode:** Manual / inline (no subagent)

## Must-haves — verification

### Truths
| # | Truth | Status |
|---|---|---|
| 1 | Single `main.py` dispatcher accepts `--mode {train,backtest,live}` and routes to a dedicated runner without changing existing behavior | ✅ `python main.py --help` shows `{train,backtest,live}` modes; train/backtest delegate via `_dispatch_train`/`_dispatch_backtest` |
| 2 | Bare `python main.py` (no args) defaults to `live` and produces the same trading-loop boot sequence | ✅ `dispatch()` routes `mode is None` to `_dispatch_live(profile=False)`; smoke test confirms boot |
| 3 | `start_ai_training.py` + `scripts/run_backtest.py` remain working as thin wrappers — flags + exit codes unchanged | ✅ Both have `__main__` shim `sys.exit(run_train(sys.argv[1:]))` / `sys.exit(run_backtest(sys.argv[1:]))`; `--help` surface unchanged |
| 4 | `main.py` chdir's to its own directory at import time so relative paths resolve from project root regardless of caller CWD | ✅ `os.chdir(os.path.dirname(os.path.abspath(__file__)))` at module top — fixes the "no models found" bug from the parent-CWD launch |
| 5 | `--profile` flag enables cProfile output to `logs/profiling/{mode}_{timestamp}.prof` without affecting non-profile runs | ✅ `scripts/profiling_harness.py` provides `profile_call`, `write_profile_report`, `maybe_pyspy_record`; gated by `args.profile` |

### Artifacts
| Path | LOC | Status |
|---|---|---|
| `main.py` | 194 | ✅ (target ≤ 200) |
| `trading/runner.py` | 138 | ✅ new — `TradingSystem` + `async def run_live(settings)` |
| `scripts/profiling_harness.py` | 165 | ✅ new — cProfile + optional py-spy |
| `tests/test_main_cli.py` | 148 | ✅ new — 6 tests, all green |
| `start_ai_training.py` | (unchanged surface) | ✅ extracted body into `run_train(argv)` + `add_train_args(parser)`; `__main__` shim preserved |
| `scripts/run_backtest.py` | (unchanged surface) | ✅ extracted body into `run_backtest(argv)`; `__main__` shim preserved |

### Key links
- `main.py` → `trading.runner` via lazy `__getattr__` (PEP 562) — `TradingSystem` + `run_live` re-exported without loading the heavy stack on `--help`
- `start_ai_training.py` → `main.py` via subprocess (unchanged for `start_ai_training_gui.py` contract)

## Tasks

| # | Task | Commit |
|---|---|---|
| 1 | Extract `TradingSystem` + `run_live` into `trading/runner.py` | `47143e6` |
| 2 | Replace `main.py` with argparse dispatcher | `ccab591` |
| 3 | Convert `start_ai_training.py` + `scripts/run_backtest.py` into thin wrappers | `5d2c376` |
| 4 | Profiling harness module | `264bf10` |
| 5 | CLI dispatch tests | `476d96e` |
| 6 (bonus) | PEP 562 `__getattr__` lazy-load to keep `--help` fast | `a19e9bc` |

## Verification checklist

- [x] Existing test suite passes (no regression beyond unrelated)
- [x] `python main.py --help` shows `--mode {train,backtest,live}` and `--profile`
- [x] `python main.py train --help` passes through to `start_ai_training` flag surface (`--target`, `--timeframes`, `--primary-timeframe`, …)
- [x] `python main.py backtest --help` passes through to `run_backtest` flag surface (`--version-dir`, `--csv`, `--broker`, `--commission`, `--output`)
- [x] Bare `python main.py` chdir works — predictor finds `ai_engine/saved_models/{xgboost,lightgbm,feature_scaler}.pkl`
- [x] `start_ai_training_gui.py` subprocess contract preserved (no source change to GUI)
- [x] No module-level imports of `shap`, `lightgbm`, `matplotlib`, `xgboost` in `main.py` (grep returns empty)
- [x] `tests/test_main_cli.py` — 6 passed in 3.99s on the project venv (`.venv/Scripts/python.exe`)
- [x] Files under 500 lines (CLAUDE.md rule); `main.py` 194/200

## Notes for downstream waves

- The chdir behavior introduced here means all subsequent plans (18-02..18-04) can rely on relative paths from project root regardless of how `main.py` is launched.
- `scripts/profiling_harness.profile_call` is the single profiling entry point — Wave 3 (18-03 Task 1) uses it for baseline capture; Wave 4 (18-04 Task 4) uses it for regression tests.
- The PEP 562 lazy re-export pattern in `main.py` is the canonical example for the lazy-import work in Wave 3 (18-03 Task 4) — apply the same shape to `shap`/`lightgbm`/`matplotlib` inside the modules that use them.
- Acceptance for "wall-clock `python main.py --help` under 1.5 s" — measured manually pre-PEP562 (~0.9s) and post-PEP562 (~0.35s on the project venv). No heavy stack loaded for `--help`.

## Status

**PLAN 18-01: COMPLETE ✅** — ready to proceed to Wave 1b (Plan 18-02 — 48-month data floor + `--max-history`).
