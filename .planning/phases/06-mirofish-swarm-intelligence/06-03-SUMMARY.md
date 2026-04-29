---
phase: 06-mirofish-swarm-intelligence
plan: "03"
subsystem: mirofish-integration
tags: [mirofish, signal-generator, lifecycle, integration-tests, veto-logic, async]
dependency_graph:
  requires:
    - mirofish-client-module (from 06-02)
    - mirofish-settings (from 06-01)
  provides:
    - mirofish-signal-integration
    - mirofish-integration-tests
  affects:
    - trading/signal_generator.py
    - trading/lifecycle.py
    - tests/test_mirofish_integration.py
tech_stack:
  added: []
  patterns:
    - Unbound method call for mixin testing (SignalGeneratorMixin._generate_signal(mock_system, ...))
    - sys.modules leaf-only stubbing (stub connection.py not the database package) to avoid test pollution
    - asyncio.get_event_loop().run_until_complete() for sync test harness
key_files:
  created:
    - tests/test_mirofish_integration.py
  modified:
    - trading/signal_generator.py
    - trading/lifecycle.py
decisions:
  - Stub only database.connection/models/signal_repo leaf modules (not parent packages) to avoid sys.modules pollution across test suite
  - HOLD signals skip check_veto entirely via guard in _generate_signal (signal.get("action") not in (None, "HOLD"))
  - No_cache case returns signal unchanged (no mirofish_veto key) matching D-16 graceful degradation
metrics:
  duration_minutes: 12
  completed_date: "2026-03-26"
  tasks_completed: 2
  files_created: 1
  files_modified: 2
---

# Phase 6 Plan 3: MiroFish Trading System Integration Summary

**One-liner:** MiroFishClient wired into lifecycle.py (background loop on startup) and signal_generator.py (synchronous veto check after ML prediction), with 6 integration tests verifying the full signal pipeline via mocked MiroFish.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Wire MiroFish into lifecycle.py (init + background task) and signal_generator.py (veto check) | 7b22d4f | trading/lifecycle.py, trading/signal_generator.py |
| 2 | Create integration tests for MiroFish signal pipeline | 87c2cd1 | tests/test_mirofish_integration.py |

## What Was Built

### Task 1: MiroFish Wired into Trading System

**trading/lifecycle.py changes:**
- `self._mirofish_client = None` and `self._mirofish_task = None` added to `__init__()` after `self._confirmation_handler`
- In `start()`: MiroFishClient initialized and `run_simulation_loop()` started as asyncio.Task when `mirofish_enabled=True`; exceptions caught with graceful degradation (D-16)
- In `stop()`: `_mirofish_task.cancel()` with `contextlib.suppress(CancelledError)` for clean shutdown
- `import contextlib` added at top of file

**trading/signal_generator.py changes:**
- After `signal = await self._ai_predictor.predict(...)`, veto check added:
  - Condition: signal is not None, action is not HOLD, `mirofish_enabled=True`, `_mirofish_client is not None`
  - Synchronous call: `signal = self._mirofish_client.check_veto(signal)`
- When `mirofish_enabled=False` (default): zero overhead, identical code path to pre-Phase 6

### Task 2: Integration Tests

`tests/test_mirofish_integration.py` (277 lines, 6 tests):

| Test | Scenario | Assert |
|------|----------|--------|
| test_signal_vetoed_when_mirofish_contradicts | BUY + swarm SELL | action=HOLD, mirofish_veto=True |
| test_signal_passes_when_mirofish_agrees | BUY + swarm BUY | action=BUY, mirofish_veto=False |
| test_signal_passes_when_mirofish_disabled | BUY + disabled | action=BUY, no mirofish_veto key |
| test_signal_passes_when_no_cached_assessment | BUY + no cache | action=BUY, no mirofish_veto key |
| test_hold_signal_never_vetoed | HOLD + swarm SELL | action=HOLD, no mirofish_veto key |
| test_mirofish_client_not_initialized_passes_signal | BUY + client=None | action=BUY, no mirofish_veto key |

**Test architecture:** Calls `SignalGeneratorMixin._generate_signal()` as an unbound method on a `types.SimpleNamespace` mock system. Uses `sys.modules` leaf-stubbing (only `database.connection`, `database.models`, `database.repositories.signal_repo`) to avoid importing sqlalchemy without polluting the `database` or `shared` package namespaces used by other tests.

## Deviations from Plan

### Auto-fixed: sys.modules Stubbing Scope

**Found during:** Task 2 implementation

**Issue:** First version of the test file registered `shared` and `database` as empty stub modules in `sys.modules`, which caused `test_regime_detector.py` (and others) to fail with "shared is not a package" when run together. The test_e2e_trading.py was already a pre-existing failure.

**Fix:** Changed stubbing strategy to only replace leaf modules (`database.connection`, `database.models`, `database.repositories.signal_repo`) without touching the `database` or `shared` parent packages. Parent packages are real on-disk packages with `__init__.py` and are imported correctly by other tests.

**Impact:** 6 integration tests pass without causing any regressions in other test files.

**Files modified:** tests/test_mirofish_integration.py (same file, no extra commit)

## Verification Results

- `python -m pytest tests/test_mirofish_client.py tests/test_mirofish_integration.py -x --tb=short -q` -- 33 passed (27 unit + 6 integration)
- `python -c "from ai_engine.mirofish_client import MiroFishClient, SwarmAssessment; print('Imports OK')"` -- OK
- `grep -q "_mirofish_client" trading/lifecycle.py` -- FOUND
- `grep -q "check_veto" trading/signal_generator.py` -- FOUND
- `grep -q "mirofish_enabled" trading/signal_generator.py` -- FOUND
- Note: `python -c "from config.settings import Settings; s = Settings(); assert s.mirofish_enabled == False"` requires project venv (pydantic_settings not in system Python) -- pre-existing limitation documented in 06-01-SUMMARY.md

## Known Stubs

None -- all integration tests exercise real code paths. The mock objects represent external dependencies (AIPredictor, DataProvider) not the modules under test.

## Self-Check: PASSED

- tests/test_mirofish_integration.py -- EXISTS (277 lines, 6 test functions)
- trading/signal_generator.py -- EXISTS (modified, check_veto present)
- trading/lifecycle.py -- EXISTS (modified, _mirofish_client + _mirofish_task present)
- Commit 7b22d4f -- EXISTS (Task 1)
- Commit 87c2cd1 -- EXISTS (Task 2)
- 33 MiroFish tests all green (27 unit + 6 integration)
- 0 regressions in test files that were passing before this plan
