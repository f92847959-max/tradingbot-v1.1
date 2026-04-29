---
phase: 09-advanced-risk-position-sizing
plan: 02
subsystem: risk
tags: [monte-carlo, simulation, risk, position-sizing, numpy]
dependency_graph:
  requires: []
  provides: [MonteCarloSimulator, SimulationResult]
  affects: []
tech_stack:
  added: []
  patterns: [vectorised-numpy-simulation, fixed-fractional-sizing, rng-seeded-reproducibility]
key_files:
  created:
    - risk/monte_carlo.py
    - tests/test_monte_carlo.py
  modified: []
decisions:
  - Use numpy.random.default_rng(seed) for reproducible simulations (not legacy np.random.seed)
  - Store max_drawdown_pcts as fraction [0,1] (not percentage) for consistent arithmetic
  - Vectorise paths dimension, iterate sequentially over trades axis — best NumPy tradeoff
  - optimal_f scans 20 candidates from 0.005 to 0.10; each uses seed+i for independent-but-deterministic runs
  - Log drawdown percentile as % in INFO log (multiply fraction by 100) for human readability
metrics:
  duration: 3 minutes
  completed_date: "2026-04-13T19:12:52Z"
  tasks_completed: 1
  tasks_total: 1
  files_created: 2
  files_modified: 0
  tests_added: 19
---

# Phase 09 Plan 02: Monte Carlo Simulation Engine Summary

Monte Carlo simulation engine with vectorised NumPy paths, drawdown distribution percentiles, ruin probability by edge strength, and optimal-f position fraction search — all 19 tests green, 0 regressions.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Monte Carlo failing tests | 39d50ea | tests/test_monte_carlo.py |
| 1 (GREEN) | Monte Carlo implementation | 3743e9e | risk/monte_carlo.py |

## What Was Built

### `risk/monte_carlo.py`

**`SimulationResult`** — dataclass with 7 fields:
- `max_drawdown_pcts`: list[float] — max drawdown fraction per path
- `final_equities`: list[float] — terminal equity per path
- `ruin_probability`: float — fraction of paths where max drawdown >= ruin_threshold
- `drawdown_percentiles`: dict — keys p50, p75, p90, p95, p99
- `return_percentiles`: dict — keys p5, p25, p50, p75, p95
- `num_paths`: int
- `num_trades`: int

**`MonteCarloSimulator`** — two public methods:

1. `simulate(win_rate, avg_win, avg_loss, num_trades, num_paths, initial_equity, position_fraction, seed)` → `SimulationResult`
   - Generates outcome matrix `(num_paths, num_trades)` in one RNG call
   - Iterates trades sequentially; updates all paths in parallel via NumPy broadcasting
   - Fixed-fractional equity: win += equity * fraction * RRR; loss -= equity * fraction
   - Tracks running peak + max drawdown per step with `np.maximum`
   - Completes 1000 paths × 200 trades in ~0.3 seconds (target was < 5s)

2. `optimal_f(win_rate, avg_win, avg_loss, num_trades, num_paths, seed)` → float
   - Searches 20 candidates: 0.005, 0.010, ..., 0.100
   - Returns fraction maximising median terminal equity

### `tests/test_monte_carlo.py`

19 tests across 6 test classes:
- `TestSimulationResultStructure` (2 tests) — dataclass fields
- `TestMonteCarloSimulatorBasic` (7 tests) — shape, keys, types
- `TestEdgeStrengthRuin` (4 tests) — strong edge (<0.1), no edge (>0.3), win=0, win=1
- `TestReproducibility` (1 test) — seed=42 identical results
- `TestPerformance` (2 tests) — 10 paths <1s, 1000 paths <5s
- `TestOptimalF` (2 tests) — range [0,1], reproducibility
- `TestNoDatabaseImports` (1 test) — AST inspection for forbidden imports

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all simulation outputs are computed from live RNG-generated sequences.

## Self-Check: PASSED

Files exist:
- `risk/monte_carlo.py` — FOUND
- `tests/test_monte_carlo.py` — FOUND

Commits verified:
- `39d50ea` (RED tests) — FOUND
- `3743e9e` (GREEN implementation) — FOUND

All 19 tests pass, 0 regressions in pre-existing test suite.
