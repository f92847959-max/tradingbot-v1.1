# Phase 18: AI Efficiency Optimization and Real Training Entry Point - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning
**Mode:** Auto (`--auto` — recommended defaults selected; review before ultraplan)

<domain>
## Phase Boundary

Two deliverables, scoped to the existing `ai_engine/` pipeline:

1. **Efficiency:** Profile the existing training pipeline (`start_ai_training.py` → `scripts/train_models.py` → `ai_engine/training/pipeline.py` → walk-forward) and optimize the measured hot paths. No speculative rewrites.

2. **Unified entry point:** Consolidate the three existing entry surfaces (`main.py` live, `start_ai_training.py` training, `scripts/run_backtest.py` backtest) behind one CLI dispatcher with `--mode {train|backtest|live}` so a single command is the canonical way to run the system end-to-end with real Capital.com data.

**Explicitly out of scope (deferred):**
- New AI features / new models / new specialists (covered by Phase 12.x family)
- Strategy/governance/risk logic changes (Phases 4, 9, 12.1)
- Distributed/cluster training, model serving APIs
- Replacing XGBoost/LightGBM (those are locked by REQUIREMENTS)

</domain>

<decisions>
## Implementation Decisions

### Entry-point structure

- **D-01:** Single dispatcher `main.py` at repo root with `--mode {train|backtest|live}`. The current trading-loop `main.py` becomes `trading/runner.py` (the `TradingSystem` class moves there); the new `main.py` is a thin CLI that imports the appropriate sub-runner. Keeps backward compatibility: `python main.py` with no args defaults to `--mode live` (current behavior).
- **D-02:** `start_ai_training.py` is **kept** as a stable script alias (it has external callers / GUI integration in `start_ai_training_gui.py`) but its body becomes `from main import run_train; sys.exit(run_train(sys.argv[1:]))` — single source of truth lives in `main.py`'s train sub-command.
- **D-03:** `scripts/run_backtest.py` likewise becomes a thin wrapper over `main.py --mode backtest`.
- **D-04:** Subcommand CLI uses `argparse` subparsers (consistent with existing `start_ai_training.py`). Each mode keeps its current flags verbatim — no breaking flag changes in this phase.

### Profiling approach

- **D-05:** Profile first, optimize second. Use `cProfile` + `pstats` for deterministic CPU profiling and `py-spy` (sampling) for the live trading loop. Walk-forward training is profiled with `cProfile` aggregated across windows.
- **D-06:** Profiling output goes under `logs/profiling/{mode}_{timestamp}.{prof,svg,txt}`. A new `python main.py --mode train --profile` flag enables it.
- **D-07:** Profiling target metric: end-to-end wall-clock for one full `start_ai_training.py --target core` run on 5m/15m/1h with the standard 6-month dataset. Baseline must be measured **before** any optimization commit. Target: ≥30% reduction in wall-clock without regressing aggregate profit factor on the existing reference dataset (PF tolerance: ±2% absolute).

### Optimization candidates (gated by profiling evidence)

- **D-08:** Walk-forward parallelism: parallelize windows **within** a timeframe via `concurrent.futures.ProcessPoolExecutor` (training is CPU-bound, sklearn/XGBoost release GIL but multiprocess is the safe & cache-friendly choice on Windows). Default `max_workers = min(n_windows, max(1, os.cpu_count() - 2))`. Gated by `--parallel-windows` flag, default `auto` (enabled when ≥4 cores). Multiprocess is OFF by default for training jobs already launched in parallel across timeframes — otherwise CPU oversubscription will hurt rather than help. Concretely: when `start_ai_training.py` launches one process per timeframe, those child processes default `--parallel-windows=1`.
- **D-09:** Feature engineering cache: cache the per-window feature matrix output of `FeatureEngineer` keyed by `(data_hash, feature_config_hash, window_start, window_end)`. Per-window `FeatureScaler` continues to be fit fresh on each window's train slice (TRAIN-02 — leakage rule preserved). Cache lives in `data/.feature_cache/` (gitignored), evictable by `--no-feature-cache` and bounded by an LRU size cap (default 4 GiB).
- **D-10:** Vectorization passes: audit `_vectorized_labeling*`, ATR/regime computation, and SHAP subsample paths for residual Python loops. Replace any survivors with NumPy / pandas vector ops only where profiling shows >5% wall-clock cost.
- **D-11:** GPU path: optional, off by default. Add `--device {cpu,cuda}` flag. When `cuda`, pass `tree_method="hist"` + `device="cuda"` to XGBoost and `device="gpu"` to LightGBM. CPU remains the reproducibility baseline; GPU results are accepted as a speed lane only when seed-fixed runs reproduce within PF ±2%.
- **D-12:** Imports & warm-start: lazy-import heavy modules (`shap`, `lightgbm`, `matplotlib`) inside the functions that use them so CLI startup for `--mode live` stays sub-second.

### Real training scope

- **D-13:** "Echtes Training" canonical configuration (the one the unified CLI must run unmodified): `--target core --timeframes 5m,15m,1h --primary-timeframe 5m --min-data-months 6 --broker`. This matches the current Phase 2 / Phase 12.7 contract — TRAIN-07 minimum is honored.
- **D-14:** No synthetic data in the real-training path. `ai_engine/training/synthetic_market.py` stays available only for unit tests and the `--smoke` subcommand (see D-19). Real training rejects synthetic data sources with a hard error.
- **D-15:** Capital.com auth via existing `.env` resolution path (`config/settings.py` + external `~/secrets/ai-trading-gold/.env`). The CLI never reads credentials from argv. If credentials are missing, `--mode train --broker` exits non-zero with the existing error message (do not invent new secret handling).

### Reproducibility & versioning

- **D-16:** Fixed RandomState seed = 42 (existing convention from Phase 3) is the default; `--seed N` overrides. Seed is written into `run_manifest.json`.
- **D-17:** Each training run writes `run_manifest.json` alongside the existing `version.json` containing: seed, git SHA (or "dirty" + uncommitted-files count), data hash (SHA256 of input CSV bytes for each timeframe), `pip freeze` digest, Python version, CPU model + count, GPU info if `--device cuda`, wall-clock per stage, cache hit rate. Existing `version.json` is not modified — manifest is additive to preserve backward compatibility with Phase 12.7 promotion logic.
- **D-18:** Version directory format stays `v{NNN}_{YYYYMMDD}_{HHMMSS}` (Phase 2 decision). Retention stays at 5 most recent (Phase 2 decision). Production pointer file remains `production.json` (Windows-compat, Phase 2 decision).

### Testing & quality gates

- **D-19:** Three test surfaces:
  1. **Smoke test** (CI-friendly, <60s): `python main.py --mode train --smoke` runs walk-forward on a tiny synthetic slice (2000 candles, 2 windows) and asserts artifacts are produced. No real broker call.
  2. **Profiling regression test** (manual / nightly): `pytest tests/profiling/test_train_baseline.py` runs the 6-month dataset and compares wall-clock against a stored baseline file. Fails the build if regression >15%.
  3. **CLI dispatch test** (CI): `pytest tests/test_main_cli.py` asserts each `--mode` parses args correctly and routes to the right runner without actually starting trading/training.
- **D-20:** No new test framework. Existing `pytest` + `pyproject.toml` `asyncio_mode=auto` config (Phase 11 decision) is used.

### Claude's Discretion

- Exact internal layout of `main.py` (single file vs `cli/` package) — pick whichever keeps `main.py` under 500 lines per project rule.
- Exact cache-key hashing helpers (`xxhash` vs `hashlib.sha256`) — pick fastest available, prefer stdlib.
- Profiling report format (text summary, flamegraph, both) — produce both when py-spy is installed, fall back to cProfile text otherwise.
- Whether to introduce a `BaseRunner` protocol/ABC for the three mode runners or keep them as plain functions — choose based on shared surface area discovered during planning.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project-level
- `.planning/PROJECT.md` — Project vision, "profitable demo trading" non-negotiable
- `.planning/REQUIREMENTS.md` — TRAIN-01..TRAIN-07 (walk-forward, scaler, min-data), BACK-01..04 (backtest contracts)
- `.planning/STATE.md` §Decisions — locked walk-forward / versioning / SHAP / governance decisions carried forward
- `.planning/ROADMAP.md` §"Phase 18" — phase entry, "Depends on: Phase 17"
- `CLAUDE.md` — Project rules: files <500 lines, no root-folder dumps, use `/scripts` /`/src` /`/tests` /`/config`

### Existing training pipeline (must read before changing)
- `start_ai_training.py` — current canonical training entry; parallelization model, flag surface
- `scripts/train_models.py` — per-timeframe trainer invoked by start_ai_training; CLI contract
- `scripts/train_exit_ai.py` — exit-AI trainer; promotion gate caller
- `scripts/run_backtest.py` — current backtest CLI; output contract (`backtest_report.json` in version dir, Phase 5)
- `ai_engine/training/pipeline.py` — walk-forward orchestration; feature_pruning + shap_importance keys
- `ai_engine/training/walk_forward.py` — window generation (anchored, dynamic count), min_train=1500, min_test=200
- `ai_engine/training/data_preparation.py` + `data_coverage.py` — TRAIN-07 preflight, manifest writers (Phase 12.7)
- `ai_engine/training/promotion_gate.py` — champion-report gate (Phase 12.7); MUST stay green after refactor
- `ai_engine/training/data_source.py` — broker CSV ingestion path
- `ai_engine/features/feature_engineer.py` — feature_cache reuse rules (correlation / sentiment override these, Phases 11–12)
- `ai_engine/features/feature_scaler.py` — per-window fresh scaler (TRAIN-02 leakage rule)
- `ai_engine/training/model_versioning.py` — version dir + production pointer convention

### Live trading entry
- `main.py` — current live entry, mixin-based `TradingSystem`
- `trading/lifecycle.py`, `trading/trading_loop.py`, `trading/signal_generator.py`, `trading/monitors.py` — mixin sources
- `config/settings.py` — pydantic-settings, .env resolution (do not bypass)
- `api/app.py` — `create_app(system)` injection — must keep working under new dispatcher

### Adjacent phases (read decisions, do not re-litigate)
- `.planning/phases/02-*/02-CONTEXT.md` — walk-forward, versioning
- `.planning/phases/03-*/03-CONTEXT.md` — SHAP, feature pruning
- `.planning/phases/05-*/05-CONTEXT.md` — backtest CLI output contract
- `.planning/phases/12-7-*/12-7-CONTEXT.md` — training-pipeline hardening, manifests, promotion gate (most recent training phase — primary reference)

### External docs (read for optimization decisions)
- XGBoost ≥2.x `tree_method=hist` + `device` docs (replaces deprecated `gpu_hist`)
- LightGBM `device_type=gpu` build prerequisites (most pip wheels are CPU-only; document if user must rebuild)
- `concurrent.futures.ProcessPoolExecutor` on Windows — `if __name__ == "__main__"` guard requirements (spawn semantics)
- `py-spy` README — recording flags, output formats

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `start_ai_training.py` — already implements per-timeframe parallel training, broker auth check, performance summary, loop mode (refetch + rebuild snapshots). Reuse its arg parser shape; do not reinvent.
- `ai_engine/training/pipeline.py` walk-forward driver — already aggregates per-window results into `result["feature_pruning"]` + `result["shap_importance"]` (Phase 3 / 12.7). New window-parallel path must produce identical aggregated output.
- `ai_engine/training/model_versioning.py` — `v{NNN}_{date}` + `production.json` pointer is the contract; manifest writer extends it, does not replace it.
- `config/settings.py` pydantic-settings — single source of truth for .env. New CLI imports `get_settings()` rather than reading env directly.
- `trading.LifecycleMixin` / `TradingLoopMixin` / etc. — the live runner is already cleanly mixin-composed; refactor only relocates them, signature-stable.

### Established Patterns
- Subprocess-based parallelism (`subprocess.Popen` + per-job stdout log file under `logs/training/{name}.log`) — already in `start_ai_training.py`. Window-level parallelism may use `ProcessPoolExecutor` instead (no log-per-window required — windows are short-lived and aggregate into one report).
- argparse with `ArgumentDefaultsHelpFormatter` — matches `start_ai_training.py`. New `main.py` follows the same idiom.
- "Real data or hard fail" — `start_ai_training.py` already raises if `--broker` is set and Capital.com creds are missing. New CLI inherits this.
- Version manifests are JSON sidecars, not embedded in models — `version.json`, `production.json`, `dataset_manifest.json`, `promotion_artifact.json` are all sidecars. `run_manifest.json` follows this pattern.
- Configs live under `config/`. Per CLAUDE.md, NEVER save working files to repo root. New profiling configs go under `config/profiling.yaml` if any are needed.

### Integration Points
- `api/app.py:create_app(system)` injects the trading system into FastAPI. Refactor must keep this call working — `main.py --mode live` reconstructs the same `TradingSystem` and hands it to `create_app`.
- `start_ai_training_gui.py` (59 KB Tk GUI) imports nothing from `start_ai_training.py` directly today but spawns it via subprocess — GUI is unaffected as long as `start_ai_training.py` keeps the same flags + exit codes.
- Phase 12.7 promotion gate (`ai_engine/training/promotion_gate.py`) reads `version.json`. Our new `run_manifest.json` is read-only-additive — promotion gate is untouched.
- Pre-existing `tests/` directory + `pyproject.toml` `[tool.pytest.ini_options]` — extend, do not duplicate. New profiling tests under `tests/profiling/`, CLI dispatch tests as `tests/test_main_cli.py`.

</code_context>

<specifics>
## Specific Ideas

- User asked for "eine Art main.py" — interpreted as a single canonical entry point, NOT a rewrite. Existing `main.py` becomes the dispatcher; existing scripts become thin aliases. Backward compatibility for `python main.py` (no args, defaults to live) is required.
- User asked for "echtes Training" — interpreted as: real Capital.com data, no synthetic shortcut in the train path, full walk-forward + SHAP + promotion gate. This is already the contract of `start_ai_training.py --target core` today.
- User asked for "effizienter" — interpreted as measurable wall-clock reduction (target 30%) with no regression on aggregate profit factor (Phase 2 best-model selection criterion). Profile-driven, not opportunistic.

</specifics>

<deferred>
## Deferred Ideas

- **Distributed / cluster training** — out of scope for v1.0 demo milestone. Belongs in a v2 "scale" milestone.
- **Model-serving API** (separate from the trading bot) — backlog candidate, not Phase 18.
- **AutoML / hyperparameter sweep automation** — Phase 12.x already covers calibration / specialists; further automation deferred.
- **Live-trading hot-reload of models** — interesting but adds operational risk; deferred to a dedicated "online learning" phase.
- **Replacing XGBoost/LightGBM with NN** — locked by existing requirements; not Phase 18.
- **GUI consolidation** (`start_ai_training_gui.py` is 59 KB) — visible quality-of-life win but UI work, deferred to a UI-phase later.

</deferred>

---

*Phase: 18-ai-efficiency-optimization-and-real-training-entry-point*
*Context gathered: 2026-05-20*
