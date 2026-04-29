---
phase: 10-smart-exit-engine
plan: 03
subsystem: exit_engine
tags: [partial-close, tp1, smart-exit]
requirements: [EXIT-04]
key_files:
  created:
    - exit_engine/partial_close.py
  modified:
    - exit_engine/__init__.py
    - tests/test_exit_engine_management.py
tests:
  command: "python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_management.py -q"
  result: "40 passed"
completed: "2026-04-22T19:39:11.730Z"
---

# Phase 10 Plan 03 Summary: TP1 Partial Close

Implemented TP1 partial-close decision logic for Phase 10.

One-liner: `evaluate_partial_close()` emits a 50% TP1 close action when price reaches TP1, and `PartialCloseManager` prevents duplicate partial closes per deal.

## What Changed

- Added `exit_engine/partial_close.py`.
- Added `tp1_reached()` for BUY/SELL trigger checks.
- Added `evaluate_partial_close()` returning `PartialCloseAction`.
- Added `PartialCloseManager` for once-per-deal TP1 tracking.
- Exported the new APIs from `exit_engine/__init__.py`.
- Added unit coverage in `tests/test_exit_engine_management.py`.

## Verification

- `python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_management.py -q` -> `40 passed`.
