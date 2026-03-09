---
phase: "04"
plan: "03"
subsystem: "strategy, risk"
tags: [regime-detection, position-sizing, atr-guard, trade-scoring]
dependency_graph:
  requires: [regime_detector, regime_params]
  provides: [regime_aware_strategy, atr_guard_sizing, regime_sl_tp]
  affects: [strategy_manager, trade_scorer, entry_calculator, position_sizing]
tech_stack:
  added: []
  patterns: [regime-adaptive-parameters, atr-volatility-guard, lazy-imports]
key_files:
  created:
    - tests/test_regime_integration.py
  modified:
    - strategy/strategy_manager.py
    - strategy/trade_scorer.py
    - strategy/entry_calculator.py
    - risk/position_sizing.py
decisions:
  - "Two-pass confidence check: base threshold fast reject, then regime-specific re-check"
  - "Default fallback regime is RANGING (safest) when mtf_data unavailable"
  - "ATR guard threshold 5.0 for Gold (normal ATR ~$1-3, triggers only during extreme events)"
  - "Lazy imports in entry_calculator convenience functions to avoid tight coupling"
metrics:
  duration: "348s"
  completed: "2026-03-08T12:51:44Z"
  tasks: 5
  tests_added: 21
  tests_total: 281
  files_changed: 5
---

# Phase 04 Plan 03: Regime-Aware Strategy Parameters and ATR Position Sizing Summary

Wired RegimeDetector into StrategyManager evaluate() pipeline with regime-specific confidence thresholds, min scores, and ADX/ATR scoring weights; added ATR guard to PositionSizer for extreme volatility protection.

## Tasks Completed

| # | Task | Commit | Key Changes |
|---|------|--------|-------------|
| 1 | Integrate regime detection into StrategyManager | c3368e0 | Added RegimeDetector instance, detect regime from 5m DF, regime-specific confidence/score thresholds, regime info in approved signal |
| 2 | Add regime-aware scoring to TradeScorer | 86e4a1f | TRENDING boosts ADX scores, RANGING reduces them, VOLATILE caps volatility score; regime=None preserves original behavior |
| 3 | Add regime convenience functions to entry_calculator | c4de0d4 | calculate_sl_tp_for_regime() and is_valid_rr_for_regime() with lazy regime_params import |
| 4 | Add ATR guard to PositionSizer | ec23cf9 | calculate_with_atr_guard() returns min_lot_size when ATR > 5.0 (extreme volatility safety net) |
| 5 | Create regime integration test suite | b765cc2 | 21 tests covering all regime-aware code paths; 281 total passing, 0 regressions |

## Deviations from Plan

None - plan executed exactly as written. Test count exceeded minimum (21 vs 14 specified).

## Key Implementation Details

### StrategyManager evaluate() Pipeline (Restructured)
1. Reject HOLD (unchanged)
2. Fast reject: confidence < base self.min_confidence (unchanged)
3. Session filter (unchanged)
4. Multi-TF alignment (unchanged)
5. Extract indicator values (unchanged)
6. **Detect regime** from 5m DataFrame (NEW)
7. **Re-check confidence** against regime-specific threshold (NEW)
8. Calculate composite score with **regime parameter** (MODIFIED)
9. Check score against **regime-specific min_score** (MODIFIED)
10. Return enriched signal with **regime** and **regime_confidence** keys (MODIFIED)

### Regime-Adjusted Scoring Weights
- **TRENDING**: ADX>=25 scores 12 (was 10), ADX>=15 scores 7 (was 5)
- **RANGING**: ADX>=40 scores 10 (was 15), ADX>=25 scores 7 (was 10), ADX>=15 scores 3 (was 5)
- **VOLATILE**: ATR ideal band narrowed to 0.8-1.2 (was 0.7-1.5), capped at 10 (was 15)

### ATR Guard
- Threshold: 5.0 for Gold (normal ATR ~$1-3)
- Triggers only during extreme events (NFP, FOMC, black swan)
- Returns min_lot_size (0.01) instead of calculated size

## Verification

- 21 new tests all passing
- 281 total tests passing (260 existing + 21 new)
- 8 pre-existing failures unchanged (test_indicators, test_risk_integration, test_risk_manager)
- Backward compatibility verified: regime=None uses original behavior throughout

## Self-Check: PASSED

All 5 files verified present. All 5 commits verified in git log.
