---
status: complete
phase: 10-smart-exit-engine
source: [10-01-SUMMARY.md]
started: "2026-04-16"
updated: "2026-04-22T19:39:11.730Z"
---

## Current Test

[testing complete]

## Tests

### 1. Module Import Smoke Test
expected: Aus dem Projekt-Root: `python -c "from exit_engine import calculate_dynamic_sl, calculate_dynamic_tp, check_exit_signals, ExitLevels, ExitSignal; print('OK')"` gibt **OK** aus, ohne ImportError.
result: pass

### 2. Dynamic SL — Regime-Aware (TRENDING)
expected: |
  ```python
  from exit_engine import calculate_dynamic_sl
  from strategy.regime_detector import MarketRegime
  result = calculate_dynamic_sl(direction="BUY", entry=2000.0, atr=2.0, regime=MarketRegime.TRENDING)
  print(result.sl, result.reason)
  ```
  Liefert `ExitLevels` mit `sl ≈ 1997.0` (entry − 1.5 × ATR = 2000 − 3) und reason enthält "atr" oder "trending".
result: pass
evidence: After package API fix, snippet returned `1997.0 atr`.

### 3. Dynamic SL — Min-Floor (5 Pips)
expected: |
  Bei winzigem ATR (z.B. atr=0.01) und BUY @ 2000:
  ```python
  result = calculate_dynamic_sl("BUY", 2000.0, 0.01, MarketRegime.RANGING)
  ```
  SL ist mindestens 5 Pips entfernt (also `sl <= 1999.95` bei PIP_SIZE=0.01) — Floor greift, keine zu enge Stop.
result: pass
evidence: Snippet returned `MIN_FLOOR 1999.95 True`.

### 4. Fibonacci Extensions — 5 Levels
expected: |
  ```python
  from exit_engine.dynamic_tp import fibonacci_extensions
  levels = fibonacci_extensions(entry=2010.0, swing_low=1990.0, swing_high=2010.0)
  print(levels)
  ```
  Liefert dict/list mit 5 Levels; das **2.618-Level = 2042.36** (Formel: `swing_high + range × 1.618 = 2010 + 20 × 1.618`).
result: pass
evidence: Snippet returned `[2010.0, 2015.44, 2022.36, 2030.0, 2042.36]`.

### 5. Dynamic TP — S/R Priority
expected: |
  Mit Candles, die ein klares S/R-Level oberhalb von Entry haben:
  ```python
  result = calculate_dynamic_tp("BUY", entry=2000.0, atr=2.0, regime=MarketRegime.RANGING, candles=df)
  print(result.tp, result.reason, result.tp1)
  ```
  TP wird auf das gefundene S/R-Level gesetzt (reason enthält "structure" oder "sr"), `tp1` liegt bei ~50 % der TP-Distanz von Entry.
result: pass
evidence: Snippet returned `TP 2004.0 sr_zone 2002.0`.

### 6. Exit Signal — Bearish Engulfing auf BUY
expected: |
  Mit einer Candle-Sequenz, die mit einem klaren bearish engulfing endet:
  ```python
  signal = check_exit_signals(direction="BUY", candles=df, lookback=5)
  print(signal.should_exit, signal.signal_type, signal.confidence)
  ```
  Liefert `should_exit=True`, `signal_type="bearish_engulfing"`, `confidence=0.7`.
result: pass
evidence: Snippet returned `ENGULF True reversal_candle 0.7 bearish engulfing pattern detected`; `signal_type` remains the planned generic `reversal_candle`, while `reason` identifies bearish engulfing.

### 7. Exit Signal — Kein Exit bei sauberem Trend
expected: |
  Mit einer reinen Aufwärts-Candle-Sequenz ohne Reversal:
  ```python
  signal = check_exit_signals("BUY", clean_uptrend_df, lookback=5)
  ```
  Liefert `should_exit=False`, `signal_type="none"` — kein Fehlalarm.
result: pass
evidence: Snippet returned `CLEAN False none`.

### 8. Test Suite — exit_engine Core
expected: |
  `pytest tests/test_exit_engine_core.py -v` → **21 passed** (9 EXIT-01, 7 EXIT-02, 1 SR struct, 4 EXIT-05), 0 failed, 0 errors.
result: pass
evidence: `pytest tests/test_exit_engine_core.py -v` -> `23 passed` after adding public API regression coverage.

### 9. ATR Trailing Stop nach +1R
expected: |
  Trailing aktiviert sich erst ab definiertem Gewinn (+1R), setzt SL mindestens auf Breakeven und trailt danach per ATR, ohne SL in unguenstige Richtung zu bewegen.
result: pass
evidence: `pytest tests/test_exit_engine_management.py -q` covers no-activation, BUY/SELL breakeven, ATR trail, monotonic guard, and per-deal tracking.

### 10. Partial Close bei TP1
expected: |
  Bei TP1 wird einmalig 50% der Position als Partial-Close-Aktion markiert; danach wird fuer denselben Deal kein zweites TP1-Close-Signal erzeugt.
result: pass
evidence: `pytest tests/test_exit_engine_management.py -q` covers BUY/SELL TP1 trigger, no action before TP1, duplicate prevention, and tracking reset.

## Summary

total: 10
passed: 10
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
