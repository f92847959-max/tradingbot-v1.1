---
phase: 10-smart-exit-engine
plan: 02
subsystem: exit_engine
tags: [trailing-stop, atr, breakeven, smart-exit]
requirements: [EXIT-03]
key_files:
  created:
    - exit_engine/trailing_manager.py
  modified:
    - exit_engine/__init__.py
    - tests/test_exit_engine_management.py
tests:
  command: "python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_management.py -q"
  result: "40 passed"
completed: "2026-04-22T19:39:11.730Z"
---

# Phase 10 Plan 02 Summary: ATR Trailing Stop

Implemented ATR-based smart trailing stop logic for Phase 10.

One-liner: `calculate_trailing_stop()` activates after +1R, moves SL to breakeven, then trails by ATR while preserving monotonic stop movement; `SmartTrailingManager` tracks accepted SL levels per deal.

## What Changed

- Added `exit_engine/trailing_manager.py`.
- Added `profit_r_multiple()` for BUY/SELL R-multiple calculation.
- Added `calculate_trailing_stop()` returning `TrailingResult`.
- Added `SmartTrailingManager` for per-deal state tracking.
- Exported the new APIs from `exit_engine/__init__.py`.
- Added unit coverage in `tests/test_exit_engine_management.py`.

## Verification

- `python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_management.py -q` -> `40 passed`.
