# Phase 15: Fibonacci Engine & S/R Zones - Research

**Researched:** 2026-04-28
**Domain:** Technical Analysis & Market Structure
**Confidence:** HIGH

## Summary

This phase focuses on building a robust "Support/Resistance Engine" that automates the detection of key market levels and structure. Unlike the basic implementation in Phase 10 (which focused on dynamic TP/SL for exits), this engine serves as a central intelligence module for both signal generation (entries) and trade management.

The core architecture moves from "lines" to "zones" using density-based clustering (MeanShift), implements automated trendline detection via Hough Transforms, and provides multi-scale Fibonacci analysis anchored by a ZigZag swing-detection algorithm. The final output is a "Confluence Map" that aggregates these disparate levels into high-probability zones, providing the AI with a structured view of market obstacles and targets.

**Primary recommendation:** Use `MeanShift` clustering for S/R zones to avoid arbitrary level counts, and the `trendln` library for robust diagonal trendline detection.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Swing Detection | API / Backend | — | Pure numerical processing of OHLC data. |
| S/R Zone Clustering | API / Backend | — | Requires scikit-learn; high compute for dense data. |
| Trendline Fitting | API / Backend | — | Uses trendln/Hough Transform; computationally intensive. |
| Confluence Scoring | API / Backend | — | Aggregates all levels into a unified data structure. |
| Visualisation (UI) | Browser / Client | — | Renders detected zones/lines on the dashboard chart. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `trendln` | 0.1.18 | Trendline & S/R lines | Industry standard for automated diagonal/horizontal lines using Hough Transforms. [VERIFIED: pip] |
| `scikit-learn` | 1.8.0 | MeanShift Clustering | Optimal for finding S/R "zones" without pre-specifying the number of levels ($K$). [VERIFIED: pip] |
| `scipy` | 1.17.1 | Peak detection | Robust local extrema identification (`argrelextrema`). [VERIFIED: pip] |
| `zigzag` | 0.3.2 | Swing detection | Standard implementation of the ZigZag algorithm for pivot identification. [VERIFIED: pip] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `numpy` | 2.2.3 | Math/Vectorisation | Core for all distance and level calculations. [ASSUMED] |
| `pandas` | 2.2.3 | Data Handling | Handling OHLC time-series data. [ASSUMED] |

**Installation:**
```bash
pip install trendln scikit-learn scipy zigzag
```

## Architecture Patterns

### System Architecture Diagram
Data flows from raw Candles through three parallel detection engines into a unified Confluence Scorer.

```
[Candle Data]
      |
      +----[ZigZag Engine] ----> [Swing Pointers] ----> [Fibonacci Levels]
      |                                                        |
      +----[S/R Engine] ------> [Local Extrema] ------> [MeanShift Zones]
      |                                                        |
      +----[Trendline Engine]-> [Hough Transform] ----> [Diagonal Lines]
      |                                                        |
      +----[Pivot Point Calc]-> [Daily/Weekly PPs] ----> [Pivot Levels]
                                                               |
                                                     [Confluence Scorer]
                                                               |
                                                     [Final Level Map]
```

### Recommended Project Structure
```
ai_engine/
├── analysis/
│   ├── confluence_engine.py  # Central aggregator and scorer
│   ├── fibonacci_engine.py   # ZigZag + Fib Retracement/Extension
│   ├── sr_engine.py          # MeanShift clustering + S/R zones
│   └── trendline_engine.py   # trendln integration
└── ...
```

### Pattern 1: MeanShift S/R Zones
**What:** Use density-based clustering on local price extrema to find "natural" support and resistance zones.
**When to use:** For all horizontal S/R detection to avoid the "too many lines" problem.
**Example:**
```python
# Source: scikit-learn MeanShift Documentation
from sklearn.cluster import MeanShift, estimate_bandwidth

def find_sr_zones(extrema_prices):
    X = np.array(extrema_prices).reshape(-1, 1)
    bandwidth = estimate_bandwidth(X, quantile=0.1)
    ms = MeanShift(bandwidth=bandwidth, bin_seeding=True)
    ms.fit(X)
    # Centers are the medians of S/R zones
    return sorted(ms.cluster_centers_.flatten())
```

### Pattern 2: Multi-Scale Swing Detection
**What:** Run ZigZag with multiple thresholds (e.g., 0.5% for Intraday, 2% for Swing).
**When to use:** To identify major structural breaks vs. minor noise.

### Anti-Patterns to Avoid
-   **Exact Line Matching:** Prices rarely respect an exact line; always use **zones** (cluster center +/- width).
-   **Look-ahead in ZigZag:** Never use the current "unconfirmed" ZigZag leg for signal generation. A pivot is only confirmed after price reverses by the threshold.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trendline fitting | Custom linear regression | `trendln` | Handles multi-point touches and slope errors natively. |
| Density Clustering | Custom distance grouping | `sklearn.MeanShift` | Automatically determines the number of clusters. |
| Local Extrema | Manual loop checks | `scipy.signal.argrelextrema` | Highly optimised for NumPy arrays. |

## Common Pitfalls

### Pitfall 1: Look-ahead Bias in ZigZag
**What goes wrong:** Backtesting shows perfect entries at peaks.
**Why it happens:** ZigZag only knows a peak was a peak *after* the price has already dropped X%.
**How to avoid:** Only anchor Fibonacci levels to **confirmed** pivots (i.e., the pivot before the current leg).

### Pitfall 2: Level Over-crowding
**What goes wrong:** The chart is covered in lines, making every price a "reversal" point.
**How to avoid:** Implement a **Confluence Score**. Only display or use levels that have at least 2-3 overlapping indicators (e.g., Fib 0.618 + S/R Zone + Pivot).

## Code Examples

### Confluence Logic (Simplified)
```python
# Source: Community Best Practice
def get_confluence_zones(levels, proximity_atr_mult=0.5, atr=1.0):
    threshold = atr * proximity_atr_mult
    zones = []
    for lvl in sorted(levels):
        if not zones or abs(lvl - zones[-1]['median']) > threshold:
            zones.append({'median': lvl, 'hits': 1})
        else:
            # Update median of existing zone
            zones[-1]['hits'] += 1
            zones[-1]['median'] = (zones[-1]['median'] + lvl) / 2
    return [z for z in zones if z['hits'] >= 2]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Rolling Min/Max | MeanShift Clustering | 2022+ | Zones are more robust than single-candle lines. |
| Fixed Pips | ATR-Normalized Zones | 2021+ | Adapts to volatility automatically. |
| Manual Fib Selection | Auto-ZigZag Anchoring | — | Removes trader subjectivity from the engine. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | NumPy/Pandas 2.2.3 compatibility | Standard Stack | Minor version mismatch might require code tweaks. |
| A2 | Capital.com Gold data density | Summary | Low data density might make MeanShift clustering less effective. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `scikit-learn`| S/R Engine | ✓ | 1.8.0 | — |
| `trendln` | Trendline Engine| ✓ | 0.1.18 | — |
| `scipy` | Peak Detection | ✓ | 1.17.0 | — |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` |
| Quick run command | `pytest tests/test_exit_engine_core.py` |
| Full suite command | `pytest tests/` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SR-01 | Detects horizontal S/R zones | Unit | `pytest tests/test_sr_engine.py` | ❌ Wave 0 |
| FIB-01 | Auto-anchors Fib to ZigZag pivots | Unit | `pytest tests/test_fib_engine.py` | ❌ Wave 0 |
| CONF-01| Identifies high-confluence zones | Integration | `pytest tests/test_confluence.py`| ❌ Wave 0 |

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | Validate all OHLC data for NaNs and extreme outliers before processing. |
| V14 Configuration | yes | Store sensitive engine parameters (thresholds) in `settings.py`. |

### Known Threat Patterns for Technical Analysis

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Data Spoofing | Spoofing | Ensure market data comes from a verified, signed source. |
| Algorithmic DoS | Denial of Service | Cap the lookback window and cluster count to prevent CPU exhaustion on MeanShift. |

## Sources

### Primary (HIGH confidence)
- `/gregorymorse/trendln` - Automated trendline calculation and visualisation.
- `scikit-learn` docs - MeanShift clustering for density estimation.
- `scipy.signal` docs - Extrema detection methods.

### Secondary (MEDIUM confidence)
- ZigZag implementation patterns from `medium.com/trading-technical-analysis`.
- Confluence scoring logic from community algorithmic trading forums.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Libraries are mature and verified via pip.
- Architecture: HIGH - Follows industry standards for TA automation.
- Pitfalls: HIGH - Addresses common algorithmic trading errors (look-ahead).

**Research date:** 2026-04-28
**Valid until:** 2026-05-28
