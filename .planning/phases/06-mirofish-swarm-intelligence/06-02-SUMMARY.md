---
phase: 06-mirofish-swarm-intelligence
plan: "02"
subsystem: mirofish-client
tags: [mirofish, httpx, async, swarm-intelligence, cost-limiter, tdd, veto-logic]
dependency_graph:
  requires:
    - mirofish-settings (from 06-01)
    - mirofish-seed-data (from 06-01)
  provides:
    - mirofish-client-module
    - swarm-assessment-type
    - veto-logic
  affects:
    - ai_engine/mirofish_client.py
    - tests/test_mirofish_client.py
tech_stack:
  added:
    - httpx.AsyncClient (already in requirements.txt at 0.28.1, now used async)
    - dataclasses (stdlib, SwarmAssessment)
    - asyncio (stdlib, background loop)
  patterns:
    - TDD (RED test file first, then GREEN implementation)
    - Graceful degradation (exceptions caught in _run_one_simulation, non-fatal)
    - German keyword matching for report parsing
    - JSON state files for cost tracking and project/graph persistence
key_files:
  created:
    - ai_engine/mirofish_client.py
    - tests/test_mirofish_client.py
decisions:
  - check_veto and veto tests implemented in same commit as core module (atomic TDD)
  - HOLD signal is not vetoed (no contradiction between HOLD and any swarm direction)
  - confidence capped at 0.9 max (not 1.0) to avoid false certainty
  - estimated_tokens hardcoded at 5000 per simulation (gpt-4o-mini estimate)
  - Offline warning fires once per offline episode via _offline_warned flag (D-17)
metrics:
  duration_minutes: 8
  completed_date: "2026-03-25"
  tasks_completed: 2
  files_created: 2
  files_modified: 0
---

# Phase 6 Plan 2: MiroFish Client Module Summary

**One-liner:** Async MiroFish REST client with full 14-step simulation pipeline, German report parser using keyword matching, daily cost limiter with JSON persistence, TTL-based result cache, and veto check method for ML signal integration.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Create MiroFishClient module with simulation pipeline, cache, cost limiter, report parser | 94c7b5b | ai_engine/mirofish_client.py, tests/test_mirofish_client.py |
| 2 | Add veto check helper method to MiroFishClient (included in Task 1 commit) | 94c7b5b | ai_engine/mirofish_client.py, tests/test_mirofish_client.py |

## What Was Built

### ai_engine/mirofish_client.py (643 lines)

**SwarmAssessment dataclass:**
- Stores `direction` (BUY/SELL/NEUTRAL), `confidence` (0.0-1.0), `reasoning` (German text), `timestamp` (monotonic)

**parse_swarm_direction(report_markdown) -> tuple[str, float, str]:**
- Counts 12 bullish and 11 bearish German keyword phrases in lowercased text
- Confidence = min(0.9, 0.5 + margin / (total * 2.0)) -- capped to prevent overconfidence
- Empty string returns ("NEUTRAL", 0.5, "Keine klare Richtung erkennbar")

**MiroFishCostLimiter:**
- JSON state file at `logs/mirofish_cost.json` with date/sim_count/tokens_used
- Auto-resets on new calendar day (date comparison in _load())
- `can_run()` checks both sim count limit and token budget
- `record_run(tokens_used)` increments both counters atomically

**MiroFishClient:**
- 9 constructor params matching settings.py fields
- `health_check()`: GET /health with 5s timeout, returns bool
- `get_cached_assessment()`: compares monotonic age vs TTL, returns Optional[SwarmAssessment]
- `_load_state()` / `_save_state()`: JSON persistence for project_id + graph_id to `logs/mirofish_state.json`
- `_ensure_graph()`: lazy graph initialization with state file fallback
- `_build_graph()`: full 3-step ontology + build + task-poll sequence
- `_run_one_simulation()`: 14-step pipeline (create -> 2x prepare -> start -> run-poll -> report -> parse); exceptions caught as non-fatal (D-16)
- `check_veto(signal)`: veto logic implementing D-06 to D-09

**run_simulation_loop(client, interval_seconds):**
- Infinite async loop with health check, cost gate, simulation trigger
- Single offline warning per outage episode (D-17)
- CancelledError re-raised for clean shutdown; all other exceptions swallowed (D-18)

### tests/test_mirofish_client.py (351 lines, 27 tests)

| Test Class | Tests | Coverage |
|-----------|-------|----------|
| TestSwarmAssessment | 3 | dataclass fields, default timestamp, custom timestamp |
| TestParseSwarmDirection | 7 | BUY signal, SELL signal, neutral, empty string, confidence cap, return type, bearish keywords |
| TestMiroFishCostLimiter | 6 | fresh state, sim limit, token limit, day reset, increment, accumulate |
| TestMiroFishClientCache | 3 | no cache, within TTL, expired TTL |
| TestMiroFishClientHealthCheck | 2 | 200 response, connection error |
| TestCheckVeto | 6 | buy blocked by sell, sell blocked by buy, neutral passthrough, agreement passthrough, no cache passthrough, HOLD unchanged |

## Deviations from Plan

### Auto-consolidated Tasks

**Task 1 + Task 2 implemented in single commit:**
- **Found during:** Implementation - check_veto and veto tests were integral to the module design
- **Reason:** The veto logic is a method on MiroFishClient; writing the class without the method would leave the class incomplete. TDD tests were written together. Both tasks share the same two files.
- **Impact:** Single commit `94c7b5b` covers all 27 tests and both tasks. No functionality was missed.

## Verification Results

- `python -c "from ai_engine.mirofish_client import MiroFishClient, SwarmAssessment, MiroFishCostLimiter, parse_swarm_direction, run_simulation_loop; print('imports OK')"` exits 0
- `python -m pytest tests/test_mirofish_client.py -x --tb=short -v` -- 27 passed
- `python -m pytest tests/test_mirofish_client.py -k "veto"` -- 6 veto tests passed
- Core regression suite (103 tests): 0 regressions
- Combined suite (118 tests): all passing

## Known Stubs

None -- all module functionality is implemented. The simulation pipeline contains real HTTP calls to MiroFish API. Integration tests are gated behind `MIROFISH_AVAILABLE` environment variable so they only run with a live backend.

## Self-Check: PASSED

- ai_engine/mirofish_client.py -- EXISTS (643 lines, exceeds 250 min)
- tests/test_mirofish_client.py -- EXISTS (351 lines, exceeds 150 min)
- Commit 94c7b5b -- EXISTS
- 27 tests all green
- 0 regressions in prior test suite
