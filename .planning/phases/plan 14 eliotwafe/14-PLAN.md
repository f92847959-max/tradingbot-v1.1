# Phase 14: Elliott Wave Theory Integration

**Goal:** Integrate automated Elliott Wave counting and Fibonacci target projection into the GoldBot 2 system to provide structural market context for both ML models and MiroFish swarm intelligence.

## Overview

This phase is divided into three waves to ensure a robust implementation of the complex Elliott Wave Theory rules.

### Wave 1: Detection Core
- **Plan:** `14-01-PLAN.md`
- **Focus:** Peak/Valley detection using `scipy.signal.find_peaks`, Elliott Wave Oscillator (EWO) implementation, and core rule validation for Impulse (1-5) and Zigzag (A-B-C) patterns.
- **Key Artifacts:** `detector.py`, `rules.py`.

### Wave 2: Fibonacci Targets & Advanced Patterns
- **Plan:** `14-02-PLAN.md`
- **Focus:** Fibonacci projection and retracement calculations, support for Diagonals, Flats, and Triangles, and a "Primary Count" selection engine based on Fibonacci confluence scoring.
- **Key Artifacts:** `fibonacci.py`, `scoring.py`.

### Wave 3: System Integration & ML Features
- **Plan:** `14-03-PLAN.md`
- **Focus:** Exposing wave states as ML features, injecting structural context into MiroFish agent prompts, and implementing signal filters/vetos in the signal generator.
- **Key Artifacts:** `elliott_wave_features.py`, `mirofish_client.py` (updated).

## Requirements Traceability

| Req ID | Description | Plan |
|--------|-------------|------|
| EWT-01 | Wave detection core (1-5, A-B-C) | 14-01 |
| EWT-02 | Fibonacci targets from wave ratios | 14-02 |
| EWT-03 | Strategy integration and ML features | 14-03 |
| EWT-04 | MiroFish structural context | 14-03 |

## Testing Strategy

1. **Unit Testing:**
   - Synthetic data tests for extrema detection and rule validation.
   - Mathematical verification of Fibonacci targets.
   - Command: `pytest tests/test_elliott_wave.py`

2. **Integration Testing:**
   - Verify feature engineering pipeline includes EW features.
   - Verify MiroFish prompt generation includes wave context.
   - Command: `pytest tests/test_feature_engineer.py`

3. **UAT / Backtesting:**
   - Run walk-forward backtests with EW features enabled to measure impact on Profit Factor and Sharpe Ratio.

## Success Criteria

- [ ] Core waves (1-5, ABC) are reliably detected in historical data.
- [ ] Fibonacci targets accurately predict reversal zones in test samples.
- [ ] ML models show positive SHAP importance for `ew_*` features.
- [ ] MiroFish agent reasoning reflects awareness of the current wave cycle.
