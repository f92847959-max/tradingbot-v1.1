# Phase 14: Elliott Wave Theory Integration - Research

**Researched:** 2026-04-28
**Domain:** Technical Analysis / Pattern Recognition / Elliott Wave Theory
**Confidence:** HIGH (Core rules and Fibonacci ratios are standard; Implementation complexity is MEDIUM-HIGH)

## Summary

Phase 14 focuses on integrating Elliott Wave Theory (EWT) into the GoldBot 2 system. This involves automatic wave counting for both motive (1-5) and corrective (A-B-C, W-X-Y) structures. Unlike traditional indicators, EWT provides a structural map of the market, allowing the bot to identify its position within a larger trend cycle.

The implementation will rely on a rule-based engine that validates price extrema (peaks and valleys) against the core "non-negotiable" rules of Elliott Wave. We will use the **Elliott Wave Oscillator (EWO)** as a momentum-based filter and the **ElliottWaveAnalyzer** framework for pattern validation. Results will be exposed as ML features (e.g., current wave, completion percentage) and integrated into the `signal_generator.py` and MiroFish swarm intelligence templates to provide structural context to the agents.

**Primary recommendation:** Use a rule-based algorithmic approach (extending `ElliottWaveAnalyzer`) rather than pure Deep Learning for wave counting to ensure adherence to strict EWT rules, then feed the identified wave state as features into the existing XGBoost/LightGBM ensemble.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Extrema Detection | API / Backend | — | Identifying peaks/valleys from OHLCV data. |
| Wave Counting Logic | API / Backend | — | Rule-based validation of wave sequences (Impulse, Zigzag, etc.). |
| Fibonacci Projections | API / Backend | — | Calculating TP/SL targets based on wave ratios. |
| ML Feature Engineering | API / Backend | — | Transforming wave state into numeric features for the ensemble. |
| Signal Integration | API / Backend | — | Using wave count as a filter/veto in `signal_generator.py`. |
| Swarm Intelligence | LLM / MiroFish | — | Passing structural wave context to MiroFish agents for reasoning. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pandas-ta` | 0.4.71b0 | Technical Indicators (EWO) | Standard for Python-based TA; includes Elliott Wave Oscillator. [VERIFIED: pypi.org] |
| `scipy` | 1.13.0+ | Extrema Detection | `scipy.signal.find_peaks` is the industry standard for peak/valley detection. [VERIFIED: scipy.org] |
| `ElliottWaveAnalyzer` | (GitHub) | Rule-based Wave Counting | Extensible framework for validating Elliott rules (1-5, ABC). [CITED: github.com/drstevendev] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `numpy` | 1.26.0+ | Numerical calculations | For Fibonacci ratio math and vector operations. |
| `matplotlib` | 3.8.0+ | Visualization | Debugging wave counts on price charts. |

**Installation:**
```bash
pip install pandas-ta scipy numpy matplotlib
# ElliottWaveAnalyzer should be integrated as a local module or cloned
```

## Architecture Patterns

### Recommended Project Structure
```
ai_engine/
├── elliott_wave/
│   ├── detector.py       # Peak/Valley detection & Wave identification logic
│   ├── rules.py          # EWT Rules (Impulse, Diagonal, Zigzag, Flat, Triangle, Complex)
│   ├── fibonacci.py      # Fibonacci projection and retracement math
│   └── models.py         # Wave state data classes (Wave, WavePattern)
├── feature_engineer.py   # Integrated wave features into ML input
└── signal_generator.py   # Use wave counts for signal filtering
```

### Wave Recognition Pipeline
1.  **Denoising:** Apply a Smoothing filter (e.g., EMA) or use the Elliott Wave Oscillator (EWO) to find "meaningful" swings.
2.  **Extrema Detection:** Use `scipy.signal.find_peaks` on the price or EWO to find local maxima and minima.
3.  **Pattern Candidate Generation:** Formulate sequences of 3 and 5 extrema.
4.  **Rule Validation:** Pass candidates through the Rule Engine (Check Rule 1, 2, 3 for Impulses, etc.).
5.  **Scoring:** Rank valid patterns based on their adherence to standard Fibonacci ratios.
6.  **State Output:** Identify the current active wave (e.g., "Motive Wave 3") and projected targets.

### Pattern 1: Wave State as ML Feature
**What:** Convert the current wave count into a vector of features.
**Features:**
- `ew_pattern_type`: (0: None, 1: Impulse, 2: Zigzag, 3: Flat, 4: Triangle, 5: Complex)
- `ew_wave_number`: (1, 2, 3, 4, 5, A, B, C, W, X, Y, Z)
- `ew_completion`: (0.0 to 1.0) - current price distance vs. projected Fibonacci target.
- `ew_is_motive`: Boolean (True for 1, 3, 5, A/C in zigzags).

### Pattern 2: MiroFish Structural Context
**What:** Pass the wave analysis as a text block to MiroFish agents.
**Example:**
> "Technical Analysis: Gold is currently in Wave 3 of a 5-wave Bullish Impulse. Wave 2 retraced 61.8% of Wave 1. Current price is at 127% extension. Targets: TP1 (161.8%) at 2345.00, TP2 (261.8%) at 2380.00."

## Detailed Wave Forms (EWT Reference)

| Category | Pattern | Sub-Waves | Core Rules / Fibonacci |
|----------|---------|-----------|------------------------|
| **Motive** | **Impulse** | 5-3-5-3-5 | W2 != >100% W1; W3 != Shortest; W4 != overlap W1. |
| **Motive** | **Diagonal** | 3-3-3-3-3* | W4 overlaps W1. Contracting: W1>W3>W5. |
| **Corrective** | **Zigzag** | 5-3-5 | B < 100% A; C usually 100% or 161.8% of A. |
| **Corrective** | **Regular Flat** | 3-3-5 | B $\approx$ A (90-105%); C $\approx$ A. |
| **Corrective** | **Expanded Flat** | 3-3-5 | B > 100% A; C > 100% B (usually 161.8% of A). |
| **Corrective** | **Triangle** | 3-3-3-3-3 | 5 waves (a-b-c-d-e). Each wave $\approx$ 61.8-78.6% of prev. |
| **Complex** | **Double Three** | W-X-Y | Linked by X wave. W, Y are any corrective pattern. |
| **Complex** | **Triple Three** | W-X-Y-X-Z | Adds another X and Z wave. |

*\*Note: Leading Diagonals can be 5-3-5-3-5, but Ending Diagonals are always 3-3-3-3-3.*

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Peak/Valley Detection | Custom loop | `scipy.signal.find_peaks` | Handles prominence and distance thresholds robustly. |
| Basic Indicators | Manual EMA/SMA | `pandas-ta` | High performance, verified implementation of EWO. |
| Rule Management | Massive `if/else` | `WaveRule` Class System | Inheriting from a base rule class (like in ElliottWaveAnalyzer) is more maintainable. |

## Common Pitfalls

### Pitfall 1: Over-Labeling (Noise)
**What goes wrong:** The algorithm identifies hundreds of tiny waves in ranging markets.
**How to avoid:** Use a "Prominence" threshold in peak detection (e.g., peak must be at least 1.5 * ATR from surrounding valleys) or filter using the EWO.

### Pitfall 2: Subjectivity & Multiple Counts
**What goes wrong:** Multiple valid wave counts exist simultaneously.
**How to avoid:** Use a scoring system based on Fibonacci Confluence. The count that matches the most Fibonacci "ideal" ratios (e.g., W2 at 61.8%, W3 at 161.8%) is selected as the Primary Count.

### Pitfall 3: Lookahead Bias in Backtesting
**What goes wrong:** Using future peaks to label current waves.
**How to avoid:** Only use data available up to the current timestamp. A wave is only "Confirmed" once a reversal of sufficient magnitude has occurred.

## Code Examples

### Peak Detection with SciPy
```python
from scipy.signal import find_peaks
import numpy as np

# Find local maxima (peaks)
peaks, _ = find_peaks(prices, distance=10, prominence=atr * 1.5)

# Find local minima (valleys) by inverting prices
valleys, _ = find_peaks(-prices, distance=10, prominence=atr * 1.5)
```

### Elliott Wave Oscillator (EWO)
```python
import pandas as pd
import pandas_ta as ta

df = pd.DataFrame(ohlcv_data)
# EWO is the difference between 5-period and 35-period SMA
df.ta.ewo(fast=5, slow=35, append=True)
# Wave 3 usually has the highest EWO value
```

### Fibonacci Target Calculation
```python
def get_fib_targets(w1_start, w1_end, w3_start):
    w1_length = abs(w1_end - w1_start)
    targets = {
        "1.618": w3_start + (w1_length * 1.618),
        "2.618": w3_start + (w1_length * 2.618),
        "4.236": w3_start + (w1_length * 4.236)
    }
    return targets
```

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Visual identification | Rule-based Algorithms | Consistency and automation. |
| Simple ABC counting | Complex (WXY) handling | Captures extended sideways markets. |
| Single "Hard" Count | Probabilistic / Scored Counts | Acknowledges market ambiguity; uses confidence scores. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ElliottWaveAnalyzer is suitable for complex patterns | Standard Stack | May require significant custom coding for WXY/WXYXZ. |
| A2 | EWO is reliable for wave identification in Gold | Summary | Gold volatility may require custom EWO parameters (e.g., 10/70 instead of 5/35). |

## Open Questions

1. **How many historical candles are needed for a valid 5-wave count?**
   - Typically 100-300 candles are needed to identify a clear cycle. We need to ensure the `DataFetcher` provides enough context.
2. **How to handle "Truncated" Wave 5s?**
   - These happen in weak markets. Rule engine needs to allow W5 < W4 high/low under specific volatility conditions.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `scipy` | Extrema detection | ✓ | 1.13.0 | — |
| `pandas-ta` | EWO Calculation | ✓ | 0.4.71b0 | Manual SMA diff |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Quick run command | `pytest tests/test_elliott_wave.py` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| EW-01 | Identify 1-5 Impulse | Unit | `pytest tests/test_elliott_wave.py::test_impulse` |
| EW-02 | Identify ABC Correction | Unit | `pytest tests/test_elliott_wave.py::test_correction` |
| EW-03 | Calculate Fib Targets | Unit | `pytest tests/test_elliott_wave.py::test_fib_targets` |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Validate OHLCV data for NaNs and outliers before wave counting. |

## Sources

### Primary (HIGH confidence)
- `drstevendev/ElliottWaveAnalyzer` (GitHub) - Rule logic reference.
- `pandas-ta` Documentation - EWO implementation.
- Elliott Wave International (elliottwave.com) - Official rules and guidelines.

### Secondary (MEDIUM confidence)
- Various Medium/Blog posts on SciPy peak detection for trading.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH
- Architecture: MEDIUM (Complexity of complex corrections)
- Pitfalls: HIGH

**Research date:** 2026-04-28
**Valid until:** 2026-05-28
