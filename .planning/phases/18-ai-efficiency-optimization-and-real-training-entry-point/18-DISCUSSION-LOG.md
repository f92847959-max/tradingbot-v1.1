# Phase 18: AI Efficiency Optimization and Real Training Entry Point - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `18-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-20
**Phase:** 18 — AI Efficiency Optimization and Real Training Entry Point
**Mode:** `--auto` (autonomous, recommended defaults selected per memory rule "Autonomous auto-decide")
**Areas discussed:** Entry-point structure, Profiling approach, Optimization candidates, Real training scope, Reproducibility & versioning, Testing & quality gates

---

## Entry-point structure

| Option | Description | Selected |
|--------|-------------|----------|
| Single `main.py` with `--mode {train,backtest,live}` subcommands; existing scripts become thin aliases | Backward-compatible default to `live`, single source of truth, matches user request "eine Art main.py" | ✓ (recommended) |
| Separate entry per mode (status quo) | No changes, less work, but doesn't satisfy user's "single entry" request | |
| Replace `start_ai_training.py` outright with new `main.py` | Cleanest, but breaks `start_ai_training_gui.py` subprocess contract and any external callers | |

**Selected:** Single dispatcher. Existing scripts kept as wrappers for backward compat.

---

## Profiling approach

| Option | Description | Selected |
|--------|-------------|----------|
| cProfile + py-spy, baseline-first, optimize-second | Deterministic + sampling complement each other; honors "no speculative rewrites" | ✓ (recommended) |
| Optimize without profiling (apply known patterns) | Faster to ship but high regression risk on PF | |
| Build a custom timing harness | Reinvents what cProfile already does | |

**Selected:** Profile first. Target: ≥30% wall-clock reduction, PF tolerance ±2%.

---

## Optimization candidates

| Option | Description | Selected |
|--------|-------------|----------|
| Walk-forward window parallelism via `ProcessPoolExecutor` | CPU-bound, Windows-safe via spawn semantics; gated by `--parallel-windows auto` | ✓ |
| Feature-matrix cache keyed by (data_hash, feature_config, window) | Per-window scaler still fits fresh (TRAIN-02 leakage rule preserved) | ✓ |
| Optional CUDA path for XGBoost/LightGBM | Off by default, CPU stays as reproducibility baseline | ✓ |
| Lazy-import heavy modules (shap, lightgbm, matplotlib) | Keeps `--mode live` cold-start sub-second | ✓ |
| Replace XGBoost/LightGBM with NN | Out of scope (locked by requirements) | |
| Distribute training across machines | Out of scope for v1.0 demo milestone | |

**Selected:** First four, all gated by profiling evidence before commit.

---

## Real training scope

| Option | Description | Selected |
|--------|-------------|----------|
| `--target core --timeframes 5m,15m,1h --primary 5m --min-data-months 6 --broker` | Matches Phase 2 / 12.7 contract, TRAIN-07 minimum | ✓ (recommended canonical) |
| Larger horizon (24 months) by default | More data ≠ better model on intraday gold; opt-in via flag, not default | |
| Include synthetic data in training | Hard-rejected — Phase 2 / 12.7 outlawed this | |

**Selected:** Canonical 6-month core run. Larger horizons remain available via `--min-data-months N`.

---

## Reproducibility & versioning

| Option | Description | Selected |
|--------|-------------|----------|
| Additive `run_manifest.json` sidecar (seed, git SHA, data hash, deps, timings) | Doesn't touch Phase 12.7 promotion-gate inputs | ✓ (recommended) |
| Embed into existing `version.json` | Risk of breaking promotion gate's expected schema | |
| Separate manifest per stage | Over-engineered for current needs | |

**Selected:** Additive sidecar. Existing `v{NNN}_{date}` + `production.json` convention unchanged.

---

## Testing & quality gates

| Option | Description | Selected |
|--------|-------------|----------|
| Smoke (`--smoke`, <60s, synthetic slice), profiling regression (manual/nightly), CLI dispatch (CI) | Three surfaces, each cheap; pytest reused | ✓ (recommended) |
| Only CI dispatch test | Cheapest but allows perf regressions to ship | |
| Full real-broker integration test in CI | Capital.com creds in CI is a security non-starter | |

**Selected:** Three test surfaces. Profiling regression is manual/nightly, not CI-blocking.

---

## Claude's Discretion (deferred to plan/execute)

- `main.py` layout (single file vs `cli/` package) — pick to stay under 500 lines per CLAUDE.md
- Cache-key hashing (`xxhash` vs `hashlib.sha256`) — stdlib preferred if perf-equivalent
- Profiling report format — both flamegraph (py-spy) + text (cProfile) when available
- Runner abstraction (Protocol/ABC vs plain functions) — decide during planning once shared surface area is mapped

## Deferred Ideas

- Distributed/cluster training (v2 milestone)
- Model-serving API (backlog)
- AutoML hyperparameter sweeps
- Live-trading hot-reload of models
- Replacing XGBoost/LightGBM with neural nets (locked out)
- GUI consolidation of `start_ai_training_gui.py` (UI phase later)
