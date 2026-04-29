---
phase: 10-smart-exit-engine
plan: "01"
subsystem: exit_engine
tags: [exit-engine, dynamic-sl, dynamic-tp, fibonacci, exit-signals, tdd]
dependency_graph:
  requires:
    - strategy/regime_detector.py (MarketRegime enum)
    - strategy/regime_params.py (REGIME_PARAMS, get_regime_params)
    - shared/constants.py (PIP_SIZE)
  provides:
    - exit_engine/types.py (ExitLevels, TrailingResult, PartialCloseAction, ExitSignal, StructureLevel)
    - exit_engine/dynamic_sl.py (calculate_dynamic_sl, find_swing_levels)
    - exit_engine/dynamic_tp.py (calculate_dynamic_tp, find_sr_levels, fibonacci_extensions)
    - exit_engine/exit_signals.py (check_exit_signals)
  affects:
    - Plan 10-02 (trailing_manager, partial_close build on these types)
    - Plan 10-03 (order_manager integration consumes these functions)
tech_stack:
  added: []
  patterns:
    - ATR * regime_sl_multiplier for regime-aware SL distance
    - Fibonacci extensions from swing_high + range * (ratio - 1.0)
    - Rolling window swing high/low detection with pandas
    - Bearish/bullish engulfing candlestick pattern detection
    - RSI divergence: price higher high vs RSI lower high comparison
key_files:
  created:
    - exit_engine/__init__.py
    - exit_engine/types.py
    - exit_engine/dynamic_sl.py
    - exit_engine/dynamic_tp.py
    - exit_engine/exit_signals.py
    - tests/test_exit_engine_core.py
  modified: []
decisions:
  - Fibonacci 2.618 level = swing_high + range * 1.618 (not 2.618); test fixed to match implementation
  - find_sr_levels clusters by 0.3% price distance, all strengths >= 1 returned (TP chooser filters by distance)
  - check_exit_signals RSI divergence uses window start vs end comparison (simple, deterministic)
  - calculate_dynamic_sl: BUY max(atr_sl, structure_sl); SELL min(atr_sl, structure_sl) — more protective
metrics:
  duration_seconds: 406
  completed_date: "2026-04-14"
  tasks_completed: 2
  files_created: 6
  tests_added: 21
---

# Phase 10 Plan 01: Exit Engine Core Summary

**One-liner:** ATR+structure dynamic SL, Fibonacci+S/R dynamic TP, and reversal candle/RSI divergence exit signals using regime-aware multipliers from REGIME_PARAMS.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Exit engine types and dynamic SL calculator | e0cc168 | exit_engine/__init__.py, exit_engine/types.py, exit_engine/dynamic_sl.py |
| 2 | Dynamic TP calculator and exit signal detector (TDD) | f1152b4 | exit_engine/dynamic_tp.py, exit_engine/exit_signals.py, tests/test_exit_engine_core.py |

## What Was Built

**exit_engine/types.py** — Five shared dataclasses:
- `StructureLevel`: support/resistance level with price, type, strength, source
- `ExitLevels`: SL + TP + optional TP1 with reason strings
- `TrailingResult`: new_sl, activated flag, profit_r, reason
- `PartialCloseAction`: close_fraction, reason, target_hit
- `ExitSignal`: should_exit, signal_type, confidence, reason

**exit_engine/dynamic_sl.py** — `calculate_dynamic_sl(direction, entry, atr, regime, structure_levels=None)`:
- Gets sl_atr_multiplier from `get_regime_params(regime)` (TRENDING=1.5, RANGING=1.0, VOLATILE=2.0)
- For BUY: `sl = max(atr_sl, structure_sl)` — most protective (closest to entry)
- For SELL: `sl = min(atr_sl, structure_sl)` — most protective
- Enforces min_sl_pips floor (default 5 pips)
- `find_swing_levels(df, lookback=20)`: detects swing highs/lows, clusters within 0.5 ATR

**exit_engine/dynamic_tp.py** — `calculate_dynamic_tp(direction, entry, atr, regime, candles=None)`:
- Priority: S/R level > Fibonacci extension > ATR-based fallback
- `fibonacci_extensions(entry, swing_low, swing_high)` → 5 levels at ratios [1.0, 1.272, 1.618, 2.0, 2.618]
- `find_sr_levels(df, lookback=50)` → swing high/low detection with 0.3% clustering
- `tp1` set at 50% of full TP distance from entry (for partial close in Plan 02)
- Falls back to `atr * tp_atr_multiplier` when no structure available

**exit_engine/exit_signals.py** — `check_exit_signals(direction, candles, lookback=5)`:
- BUY exits: bearish engulfing (confidence 0.7), shooting star (0.65), RSI bearish divergence (0.6)
- SELL exits: bullish engulfing (0.7), hammer (0.65), RSI bullish divergence (0.6)
- Returns `ExitSignal(should_exit=False, signal_type="none")` when nothing detected

## Test Results

21 tests in `tests/test_exit_engine_core.py`, all passing:
- 9 tests for EXIT-01 (dynamic SL: regime-aware, structure-adjusted, min floor, BUY/SELL direction, ATR=0 guard)
- 7 tests for EXIT-02 (Fibonacci extensions, dynamic TP: BUY/SELL direction, ATR fallback, TP1 at 50%)
- 1 test for find_sr_levels structure
- 4 tests for EXIT-05 (bearish engulfing, bullish engulfing, RSI divergence, no-exit clean trend)

No regressions introduced (pre-existing failures in test_risk_integration.py and test_risk_manager.py confirmed pre-existing from Phase 9 — not related to exit_engine).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fibonacci test expected wrong value for 2.618 level**
- **Found during:** Task 2 RED phase (test run)
- **Issue:** Test expected `2043.16` for 2.618 extension but correct math gives `2042.36` (`2010 + 20 * 1.618`)
- **Fix:** Corrected test assertion to `2042.36`
- **Files modified:** tests/test_exit_engine_core.py
- **Commit:** f1152b4

## Known Stubs

None — all functions are fully implemented with real logic. No hardcoded empty values or placeholder returns.

## Self-Check: PASSED

- [x] exit_engine/__init__.py exists
- [x] exit_engine/types.py exists
- [x] exit_engine/dynamic_sl.py exists
- [x] exit_engine/dynamic_tp.py exists
- [x] exit_engine/exit_signals.py exists
- [x] tests/test_exit_engine_core.py exists (21 tests, all pass)
- [x] Commit e0cc168 exists (Task 1)
- [x] Commit f1152b4 exists (Task 2)
