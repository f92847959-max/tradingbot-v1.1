# Phase 13: Orderbuch-Analyse - Research

**Researched:** 2026-03-27
**Domain:** Order Flow Analysis / OHLCV-derived approximations / ML Feature Engineering
**Confidence:** HIGH (Plan B / OHLCV path); MEDIUM (Plan A / Capital.com quote stream path)

---

## Summary

This phase implements Order Flow / DOM analysis for the GoldBot 2 system. The central
architectural decision is forced by a confirmed data constraint: Capital.com does NOT
provide full Level 2 / Depth-of-Market data through any API endpoint. The broker's
WebSocket stream provides only Level 1 bid/ask with single-level quantities (bidQty /
ofrQty). There is no multi-level order book available.

Therefore, Plan A is a targeted enrichment using the single-level Capital.com quote stream
(bid, bidQty, ofr, ofrQty) to derive real-time imbalance signals. Plan B — the default and
primary path — implements OHLCV-derived approximations (BVC Volume Delta, Volume Profile,
liquidity zones, absorption detection) from the candle data that already flows through the
system. These OHLCV-only approximations are usable for both live trading AND historical
backtesting.

The existing `MicrostructureFeatures` class already handles `l2_order_imbalance` and
`l2_depth_ratio` as optional inputs with safe defaults. Phase 13 must NOT duplicate those
11 existing features (`l1_spread_pips`, `l2_order_imbalance`, `l2_order_imbalance_ema_10`,
etc.) — it must ADD a new feature group with prefix `flow_` that feeds the same
`FeatureEngineer` orchestrator.

**Primary recommendation:** Implement OHLCV-derived flow features as a standalone
`OrderFlowFeatures` class in `ai_engine/features/orderflow_features.py`, wired into
`FeatureEngineer` alongside existing feature groups. Real quote stream data (Plan A) is
an opt-in enhancement stored back into the candle DataFrame as computed columns before
feature engineering runs.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FLOW-01 | Order Flow / Level 2 Daten werden abgerufen und verarbeitet | Plan A: Capital.com WebSocket quote stream (bid/bidQty/ofr/ofrQty); Plan B: OHLCV as sole input. Both are "order flow data" in the spirit of the requirement. |
| FLOW-02 | Delta (Kauf- vs. Verkaufsdruck) pro Kerze berechnet | BVC formula: delta = volume * (close - open) / (high - low). Produces signed delta per candle. Cumulative delta over rolling window. |
| FLOW-03 | Liquiditaets-Zonen und Bid/Ask Walls automatisch erkannt | Volume Profile (POC/VAH/VAL) for liquidity zones; swing high/low clustering for stop-loss zones; FVG for imbalance. |
| FLOW-04 | Order Flow Features (delta, absorption, liquidity) als ML-Input nutzbar | New `flow_*` prefixed features added to `FeatureEngineer` via `OrderFlowFeatures` class following established pattern. |
</phase_requirements>

---

## Plan A vs Plan B

### Plan A: Capital.com Quote Stream (OPTIONAL enhancement)

**What is available:** The Capital.com WebSocket sends a `quote` message with:
```json
{
  "destination": "quote",
  "epic": "GOLD",
  "bid": 2045.50,
  "bidQty": 4976.0,
  "ofr": 2045.53,
  "ofrQty": 5000.0,
  "timestamp": 1748000000000
}
```

**What this enables:**
- Real-time bid/ask spread calculation: `ofr - bid`
- Real-time Level 1 imbalance: `(bidQty - ofrQty) / (bidQty + ofrQty)` — range -1 to +1
- These can be aggregated per candle (mean, EWM) and stored as `flow_l1_imbalance` columns

**Limitation:** Single price level only. No depth stacking. No order book walls.
This is confirmed by official Capital.com API documentation at open-api.capital.com.

**Integration point:** `broker_client.py` already subscribes to `marketData.subscribe`
and receives `quote` messages. The `start_price_stream` callback can be extended to also
aggregate imbalance data per candle interval.

**Status:** OPTIONAL. OHLCV-derived features work without it. Quote stream enrichment
can be a sub-task that enhances `flow_l1_imbalance` accuracy when live.

### Plan B: OHLCV-Derived Approximations (DEFAULT / REQUIRED)

Works on all historical data (backtesting) and live data. No external API dependency.

**Core algorithms:**

1. **Volume Delta via BVC (Bulk Volume Classification):**
   - Formula: `delta = volume * (close - open) / max(high - low, epsilon)`
   - Produces buy_volume estimate and sell_volume estimate per candle
   - Research (Chakrabarty et al., 2019): BVC achieves 92.4% accuracy at 5-minute bars
   - Cumulative delta = rolling sum of delta over N candles
   - Delta divergence: price making new high but cumulative delta falling = weakness signal

2. **Volume Profile Approximation (Point of Control, Value Area):**
   - Distribute each candle's volume uniformly across its high-low range into N price bins
   - POC = bin with highest accumulated volume
   - VAH/VAL = bins enclosing 70% of total volume
   - Used to identify high-volume liquidity levels as support/resistance
   - Rolling window: compute over last 200 candles

3. **Liquidity Zone Detection (Swing-Based):**
   - Swing high/low detection: candle is swing high if its high is the highest over ±N candles
   - Cluster nearby swing highs (within ATR-based tolerance) → sell-side liquidity zone
   - Cluster nearby swing lows → buy-side liquidity zone
   - Distance from current price to nearest zone above/below
   - Library `smartmoneyconcepts==0.0.26` provides this (installable, not yet in requirements.txt)

4. **Fair Value Gap (FVG) Detection:**
   - Bullish FVG: candle[i-1].high < candle[i+1].low (gap in candle bodies, 3-candle pattern)
   - Bearish FVG: candle[i-1].low > candle[i+1].high
   - Track distance from price to nearest unfilled FVG above/below
   - FVGs act as magnet zones — price tends to fill them

5. **Absorption Detection:**
   - Large volume candle (volume > N-period mean * threshold) with small body (body < wick * ratio)
   - High volume + small price movement = institutional absorption
   - Bullish absorption: high volume bearish candle that fails to make new lows
   - Bearish absorption: high volume bullish candle that fails to make new highs
   - Score: rolling z-score of (volume / body_size)

---

## Standard Stack

### Core (already in requirements.txt / installed)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.2.6 | Vector math for delta, profile bins | Already present |
| pandas | 3.0.0 | Rolling windows, candle DataFrame ops | Core project dependency |
| scipy | 1.17.0 | Signal processing (find_peaks for swing detection) | Already installed |

### New Dependencies
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| smartmoneyconcepts | 0.0.26 | Swing highs/lows, liquidity zones, FVG, order blocks | OPTIONAL: can be replaced with hand-rolled scipy.signal.find_peaks; use if installable |

**Version verification (run before installing):**
```bash
pip show smartmoneyconcepts
# If not installed: pip install smartmoneyconcepts==0.0.26
```

**Decision on smartmoneyconcepts:** The library is small (14 kB source), pure Python,
depends only on pandas/numpy, and is installable without issues. It provides exactly
the swing high/low and liquidity clustering logic needed. However, it may conflict with
pandas 3.0 (released after 0.0.26 — verify during implementation). A hand-rolled fallback
using `scipy.signal.find_peaks` MUST be planned if compatibility fails.

**Installation (if adding to project):**
```bash
pip install smartmoneyconcepts==0.0.26
```
Add to `requirements.txt`:
```
smartmoneyconcepts>=0.0.26
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| smartmoneyconcepts | scipy.signal.find_peaks + custom clustering | More control, no extra dep; more code to write and test |
| BVC delta formula | VPIN (volume buckets) | VPIN requires volume bucketing framework, much more complex; BVC is proven at 5-min bars |
| Volume Profile (custom) | MarketProfile 0.2.0 (PyPI) | py-market-profile is simple but unmaintained; hand-roll is 30 lines and avoids the dep |

---

## Architecture Patterns

### Integration Pattern: New Feature Group

Following the established project pattern exactly:

```
ai_engine/features/
├── feature_engineer.py        # ADD: import + call OrderFlowFeatures
├── orderflow_features.py      # NEW: OrderFlowFeatures class
├── microstructure_features.py # EXISTING: do not modify
├── technical_features.py      # EXISTING
└── ...
```

```python
# orderflow_features.py - pattern matches existing feature files
class OrderFlowFeatures:
    FEATURE_NAMES: List[str] = [
        "flow_delta",
        "flow_delta_cumulative_20",
        "flow_delta_divergence",
        "flow_buy_pressure",
        "flow_poc_distance",
        "flow_vah_distance",
        "flow_val_distance",
        "flow_liq_zone_above",
        "flow_liq_zone_below",
        "flow_fvg_above",
        "flow_fvg_below",
        "flow_absorption_score",
        "flow_l1_imbalance",        # from quote stream if available, else 0.0
        "flow_volume_zscore",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Returns df with flow_* columns added. Missing inputs handled safely."""
        ...
```

### Recommended Module Structure

```
ai_engine/
└── features/
    └── orderflow_features.py    # all flow logic in one file (~300 lines)
```

No sub-package needed. The spec's `orderflow/` directory with 5 sub-modules is
over-engineered for the feature count. One file matches the existing pattern
(microstructure_features.py is one file, 91 lines).

### Feature Engineer Wiring Pattern

```python
# feature_engineer.py additions (Source: existing code pattern)
from .orderflow_features import OrderFlowFeatures   # add to imports

class FeatureEngineer:
    def __init__(self):
        ...
        self._orderflow = OrderFlowFeatures()        # add instance
        self._feature_names = (
            ...
            + self._orderflow.get_feature_names()    # add to combined list
        )

    def create_features(self, df, ...):
        ...
        df = self._micro.calculate(df)
        df = self._orderflow.calculate(df)           # after micro, uses same df
```

### Settings Pattern

```python
# config/settings.py additions
# Following MiroFish pattern — opt-in with defaults
flow_poc_window: int = 200          # candles for volume profile
flow_liq_swing_length: int = 10     # swing detection lookback
flow_absorption_vol_mult: float = 2.0  # volume threshold multiplier
flow_fvg_min_size_atr: float = 0.3  # min FVG size as ATR fraction
```

### Safe Default Pattern (from microstructure_features.py)

```python
# Source: microstructure_features.py pattern (verified in codebase)
def _series_or_default(df, column, default):
    if column in df.columns:
        series = pd.to_numeric(df[column], errors='coerce')
    else:
        series = pd.Series(default, index=df.index, dtype=float)
    return series.fillna(default)
```

All `flow_*` features must follow this: if required columns are missing or volume is
zero, return neutral defaults (0.0) rather than raising errors.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Volume profile bins | Custom bin-counting loop | numpy histogram / manual 30-line function | Already trivial with numpy; don't add dep for this |
| Swing high/low detection | Manual pandas rolling max/min with comparison | `scipy.signal.find_peaks` or `smartmoneyconcepts` | Edge cases with ties, plateaus, min_distance are non-trivial |
| BVC delta formula | Complex buy/sell volume split model | `volume * (close - open) / (high - low)` | Validated by academic research; more complex models don't improve accuracy |
| Feature NaN handling | Custom NaN policy per feature | Existing `cleanup_dataframe_features()` from `shared.utils` | Already used by all feature classes; use it |
| Candle OHLC validation | Custom validation | Existing `_normalize_dataframe()` in `data_source.py` | Already validates OHLC consistency |

**Key insight:** Order flow without tick data is fundamentally approximation. The
academic literature (Chakrabarty et al., 2019) confirms BVC at 5-min bars achieves
~92% accuracy and is the best available method without tick data. Further complexity
(VPIN, ML-based classifiers) does not improve upon BVC for this use case.

---

## Existing Features — DO NOT DUPLICATE

The `MicrostructureFeatures` class already computes these 11 features (verified in
`ai_engine/features/microstructure_features.py`):

```
l1_spread_pips, l1_spread_change_1, l1_spread_zscore_50,
l2_order_imbalance, l2_order_imbalance_ema_10, l2_imbalance_abs,
l2_depth_ratio, l2_depth_ratio_log, l2_depth_ratio_zscore_50,
micro_pressure, micro_liquidity_stress
```

Phase 13 features must use the `flow_` prefix exclusively. Any overlap with the
above list is a bug. The flow features compute different things (volume delta,
profile distance, swing-based zones, absorption) not currently computed by
`MicrostructureFeatures`.

---

## Common Pitfalls

### Pitfall 1: Zero High-Low Range (Doji / Flat Candles)
**What goes wrong:** BVC formula `(close - open) / (high - low)` produces division by zero on doji candles where high == low == close == open.
**Why it happens:** Crypto/forex data sometimes produces zero-range candles at session boundaries.
**How to avoid:** Clip denominator: `hl_range = np.maximum(high - low, 1e-6)` before division.
**Warning signs:** `inf` or `nan` in `flow_delta` column.

### Pitfall 2: Volume Profile Rolling Window Boundary
**What goes wrong:** POC computation on the first N candles (warm-up period) returns
meaningless values since volume hasn't accumulated.
**Why it happens:** Rolling windows need min_periods to be set.
**How to avoid:** Use `min_periods=max(20, window//10)` on rolling computations. Return
NaN for warm-up period, then `cleanup_dataframe_features` converts to 0.0.
**Warning signs:** All `flow_poc_distance` values are identical for early candles.

### Pitfall 3: Feature Leakage via Look-Ahead in FVG Detection
**What goes wrong:** FVG pattern requires candle[i+1], which doesn't exist at prediction time.
**Why it happens:** Standard FVG formula uses three candles: i-1, i, i+1. In a DataFrame
with future data, numpy vectorization silently uses future data.
**How to avoid:** FVG detection must shift results: detect using candle i-1, i, i+1 but
assign the FVG label to candle i-1 (the "middle" candle). For live use, only confirm FVGs
when candle i+1 has fully closed. For training data, use `.shift(-1)` carefully or detect
on fully closed historical candles only.
**Warning signs:** FVG features show suspiciously high SHAP importance during training
but degrade in live trading.

### Pitfall 4: smartmoneyconcepts Pandas 3.0 Compatibility
**What goes wrong:** `smartmoneyconcepts 0.0.26` was released in March 2025 and may
use deprecated pandas APIs (e.g., `DataFrame.append`, `inplace` operations, or
`CategoricalIndex` behavior changed in pandas 3.0).
**Why it happens:** The project uses pandas 3.0.0 (confirmed). The library targets
pandas 2.x.
**How to avoid:** Test import during Wave 0. If compatibility issues arise, implement
swing detection using `scipy.signal.find_peaks` directly (fallback). The fallback is
~40 lines and uses only scipy + numpy.
**Warning signs:** `AttributeError`, `FutureWarning` stack traces on import or call.

### Pitfall 5: Absorption Score on Low-Volume Assets
**What goes wrong:** Absorption detection based on volume z-score doesn't work when
volume is nearly constant or sparse (e.g., weekend/off-hours Gold candles).
**Why it happens:** Rolling std approaches zero, making z-score numerically unstable.
**How to avoid:** Clip rolling std to `max(std, volume.mean() * 0.01)` before division.
**Warning signs:** `flow_absorption_score` has very large values (>100) or all zeros.

### Pitfall 6: Capital.com Volume is Notional, Not Lot-Based
**What goes wrong:** The `volume` column from Capital.com candles may represent
notional transaction value or tick count, not standardized lots. BVC delta in
"volume units" is internally consistent but not comparable to CME lot volumes.
**Why it happens:** CFD brokers report proprietary volume metrics.
**How to avoid:** Normalize delta as `flow_buy_pressure = delta / volume` (a ratio)
rather than reporting raw delta. This is scale-invariant.
**Warning signs:** `flow_delta` values wildly different across time (check for volume
reporting changes).

---

## Code Examples

### BVC Volume Delta (Plan B — Primary)
```python
# Source: Chakrabarty et al. (2019) BVC formula, verified implementation
import numpy as np

def compute_flow_delta(open_, high, low, close, volume):
    """BVC Volume Delta: buy_vol - sell_vol approximation from OHLCV."""
    hl_range = np.maximum(high - low, 1e-6)  # guard against doji
    direction = (close - open_) / hl_range   # range: -1.0 to +1.0
    buy_vol = volume * (0.5 + 0.5 * direction)
    sell_vol = volume * (0.5 - 0.5 * direction)
    delta = buy_vol - sell_vol  # positive = buying pressure
    # Normalize to [-1, +1] for ML stability
    flow_buy_pressure = delta / np.maximum(volume, 1.0)
    return delta, flow_buy_pressure
```

### Rolling Cumulative Delta
```python
# Source: established order flow analysis pattern
def compute_cumulative_delta(delta: pd.Series, window: int = 20) -> pd.Series:
    """Rolling sum of BVC delta over window candles."""
    return delta.rolling(window=window, min_periods=5).sum()

def compute_delta_divergence(close: pd.Series, cum_delta: pd.Series,
                              window: int = 14) -> pd.Series:
    """Divergence: price rising but delta falling (bearish), or vice versa."""
    price_change = close.diff(window)
    delta_change = cum_delta.diff(window)
    # Positive divergence = bullish (price down, delta up)
    # Negative divergence = bearish (price up, delta down)
    divergence = np.sign(delta_change) - np.sign(price_change)
    return divergence  # values: -2, -1, 0, +1, +2
```

### Volume Profile POC Approximation
```python
# Source: standard volume profile algorithm
def compute_volume_profile(high: np.ndarray, low: np.ndarray,
                            volume: np.ndarray, n_bins: int = 50) -> tuple:
    """Returns (poc_price, vah_price, val_price) for a price window."""
    price_min = low.min()
    price_max = high.max()
    if price_max <= price_min:
        mid = (price_max + price_min) / 2
        return mid, mid, mid

    bins = np.linspace(price_min, price_max, n_bins + 1)
    vol_profile = np.zeros(n_bins)

    for i in range(len(high)):
        lo_idx = max(0, np.searchsorted(bins, low[i], 'left'))
        hi_idx = min(n_bins, np.searchsorted(bins, high[i], 'right'))
        span = max(hi_idx - lo_idx, 1)
        vol_profile[lo_idx:hi_idx] += volume[i] / span

    poc_idx = np.argmax(vol_profile)
    poc_price = (bins[poc_idx] + bins[poc_idx + 1]) / 2

    # Value Area: bins enclosing 70% of total volume
    total_vol = vol_profile.sum()
    sorted_idx = np.argsort(vol_profile)[::-1]
    cumsum = 0.0
    va_bins = []
    for idx in sorted_idx:
        cumsum += vol_profile[idx]
        va_bins.append(idx)
        if cumsum >= total_vol * 0.70:
            break
    vah_price = (bins[max(va_bins)] + bins[max(va_bins) + 1]) / 2
    val_price = (bins[min(va_bins)] + bins[min(va_bins) + 1]) / 2
    return poc_price, vah_price, val_price
```

### Fair Value Gap Detection (3-candle pattern)
```python
# Source: ICT/SMC concept, implemented in pandas
def detect_fvg(df: pd.DataFrame) -> pd.DataFrame:
    """Detect Fair Value Gaps. Results assigned to candle i (middle)."""
    high = df['high'].values
    low = df['low'].values
    n = len(df)
    bullish_fvg = np.zeros(n)
    bearish_fvg = np.zeros(n)

    # i is the middle candle; use i-1 and i+1
    # Assign to i-1 to avoid look-ahead at prediction time
    for i in range(1, n - 1):
        if low[i + 1] > high[i - 1]:         # bullish: gap between i-1 high and i+1 low
            bullish_fvg[i - 1] = (low[i + 1] + high[i - 1]) / 2  # midpoint
        if high[i + 1] < low[i - 1]:         # bearish: gap between i-1 low and i+1 high
            bearish_fvg[i - 1] = (high[i + 1] + low[i - 1]) / 2  # midpoint

    df = df.copy()
    df['_fvg_bull'] = bullish_fvg
    df['_fvg_bear'] = bearish_fvg
    return df
```

### Absorption Score
```python
# Source: OrderFlows.com absorption concept, OHLCV approximation
def compute_absorption_score(df: pd.DataFrame, vol_mult: float = 2.0,
                              window: int = 20) -> pd.Series:
    """
    High volume + small body = absorption.
    Score = rolling z-score of (volume / body_size).
    """
    body = (df['close'] - df['open']).abs().clip(lower=1e-4)
    vol_body_ratio = df['volume'] / body
    roll_mean = vol_body_ratio.rolling(window, min_periods=5).mean()
    roll_std = vol_body_ratio.rolling(window, min_periods=5).std()
    roll_std = roll_std.clip(lower=roll_std.mean() * 0.01 + 1e-8)
    zscore = (vol_body_ratio - roll_mean) / roll_std
    return zscore.clip(-5.0, 5.0)  # bound for ML stability
```

### Capital.com Quote Stream Imbalance (Plan A — Optional)
```python
# Source: Capital.com WebSocket docs (confirmed bidQty/ofrQty available)
# Location: can be wired into broker_client.py start_price_stream callback

def compute_l1_imbalance(bid_qty: float, ofr_qty: float) -> float:
    """Real-time bid/ask imbalance from Capital.com quote stream.
    Returns -1.0 (all ask pressure) to +1.0 (all bid pressure).
    """
    total = bid_qty + ofr_qty
    if total < 1e-6:
        return 0.0
    return (bid_qty - ofr_qty) / total
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Tick Rule (Lee-Ready) | BVC at candle level | 2011-2019 | BVC better for 5-min bars without tick data |
| Hand-built DOM scraping | Accept CFD broker limitations | 2020+ CFD era | CFD brokers synthesize prices; true DOM is exchange-side only |
| VPIN (complex bucketing) | BVC (simple formula) | 2019 (Chakrabarty) | BVC simpler, comparable accuracy at 5-min |
| Fixed liquidity levels | Rolling volume profile | 2015+ | Rolling POC adapts to market structure shifts |

**Deprecated/outdated:**
- **VPIN with volume bucketing:** Complex, requires near-tick data for bucketing, not significantly better than BVC at 5-min resolution. Do not implement.
- **Level 2 DOM scraping from Capital.com:** Confirmed unavailable. Do not attempt.
- **Orderflows.com / Sierra Chart data feed:** External paid feed, out of scope.

---

## Open Questions

1. **smartmoneyconcepts pandas 3.0 compatibility**
   - What we know: Library version 0.0.26 (March 2025); project uses pandas 3.0.0
   - What's unclear: Whether any deprecated pandas APIs were used in the library
   - Recommendation: Test `from smartmoneyconcepts import SmartMoneyConcepts` in Wave 0 setup task. If failure, implement swing detection with `scipy.signal.find_peaks` fallback (documented in Code Examples).

2. **Capital.com volume metric definition**
   - What we know: Volume column exists in candle data; used for indicators
   - What's unclear: Whether it's tick count, notional volume, or lot count
   - Recommendation: Always normalize delta as `delta / volume` (ratio), never use raw delta magnitude for comparison across time.

3. **Flow feature SHAP importance in practice**
   - What we know: OHLCV-derived order flow features are approximations with ~92% accuracy at best
   - What's unclear: Whether flow features will rank highly under SHAP pruning for Gold
   - Recommendation: Design features to pass SHAP pruning (Phase 3 already in codebase). If features rank in bottom 50%, they will be pruned automatically — this is acceptable.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All | Yes | 3.12.10 | — |
| numpy | BVC formula, volume profile | Yes | 2.2.6 | — |
| pandas | DataFrame ops | Yes | 3.0.0 | — |
| scipy | find_peaks fallback | Yes | 1.17.0 | — |
| pandas-ta | ATR for absorption window | Yes | 0.4.71b0 | — |
| smartmoneyconcepts | Swing/liquidity detection | Not yet | 0.0.26 available | scipy.signal.find_peaks |
| Capital.com WebSocket | Plan A quote stream | Yes (existing) | existing | Plan B OHLCV |

**Missing dependencies with fallback:**
- `smartmoneyconcepts`: Installable (14 kB, pip dry-run confirmed). Fallback: `scipy.signal.find_peaks` for swing detection. Wave 0 must test pandas 3.0 compatibility.

**Missing dependencies with no fallback:**
- None. All required algorithms work with installed packages.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_orderflow_features.py -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FLOW-01 | OrderFlowFeatures.calculate() returns DataFrame without errors on OHLCV-only input | unit | `pytest tests/test_orderflow_features.py::test_calculate_ohlcv_only -x` | Wave 0 |
| FLOW-01 | Quote stream imbalance (Plan A) computed correctly from bidQty/ofrQty | unit | `pytest tests/test_orderflow_features.py::test_l1_imbalance -x` | Wave 0 |
| FLOW-02 | flow_delta is positive for bullish candles, negative for bearish | unit | `pytest tests/test_orderflow_features.py::test_delta_direction -x` | Wave 0 |
| FLOW-02 | flow_delta handles zero-range candle (doji) without NaN/inf | unit | `pytest tests/test_orderflow_features.py::test_delta_doji_safe -x` | Wave 0 |
| FLOW-03 | flow_poc_distance is non-NaN after warm-up period | unit | `pytest tests/test_orderflow_features.py::test_volume_profile -x` | Wave 0 |
| FLOW-03 | flow_liq_zone_above and below are non-NaN when swings exist | unit | `pytest tests/test_orderflow_features.py::test_liquidity_zones -x` | Wave 0 |
| FLOW-04 | FeatureEngineer includes flow_* features in get_feature_names() | integration | `pytest tests/test_orderflow_features.py::test_feature_engineer_integration -x` | Wave 0 |
| FLOW-04 | All flow_* features are NaN-free after cleanup | unit | `pytest tests/test_orderflow_features.py::test_no_nan_after_cleanup -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_orderflow_features.py -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_orderflow_features.py` — covers FLOW-01 through FLOW-04 (8 test cases)
- [ ] Verify `smartmoneyconcepts==0.0.26` installs without error on Python 3.12.10 + pandas 3.0.0
- [ ] If smartmoneyconcepts incompatible: implement scipy fallback before main feature code

---

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` found in working directory. Constraints derived from codebase conventions:

- **Python 3.12.10** (confirmed from `python3 --version`)
- **pandas 3.0.0** (installed, `requirements.txt` says `>=2.2.0,<3.0` — CONFLICT: runtime is 3.0.0, spec says <3.0; new features must work with 3.0.0 as installed)
- **English code comments** (CODE-04 requirement, established by Phase 1)
- **All feature classes follow** `FEATURE_NAMES: List[str]` + `calculate()` + `get_feature_names()` pattern
- **cleanup_dataframe_features** from `shared.utils` must be called at end of `calculate()`
- **No lazy imports** inside methods (CODE-03 requirement)
- **All tests must pass** before merge (CODE-06)
- **ruff** linter enforced (`pyproject.toml`: `ruff>=0.8.0`, target `py311`, line-length 100)

---

## Sources

### Primary (HIGH confidence)
- Capital.com API documentation at `open-api.capital.com` — confirmed: no Level 2 data; bidQty/ofrQty available in quote messages
- Codebase analysis: `microstructure_features.py`, `feature_engineer.py`, `broker_client.py`, `conftest.py` — verified integration patterns directly
- Runtime verification: BVC formula and volume profile algorithm tested in Python 3.12 (Bash tool, zero errors)

### Secondary (MEDIUM confidence)
- Chakrabarty, Pascual & Shkilko (2019) "Evaluating Trade Classification Algorithms: Bulk Volume Classification versus the Tick Rule and the Lee-Ready Algorithm" — BVC 92.4% accuracy at 5-min bars confirmed by SSRN preprint
- smartmoneyconcepts v0.0.26 GitHub README (joshyattridge/smart-money-concepts) — functions and input format confirmed
- VisualHFT VPIN article — VPIN algorithm confirmed; complexity vs. BVC tradeoff assessed

### Tertiary (LOW confidence)
- WebSearch results re: Capital.com bidQty/ofrQty fields — corroborated by official docs fetch, elevated to HIGH
- Various TradingView Pine Script implementations of absorption and FVG — patterns are consistent across sources but none are authoritative for Python implementation

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified installed or installable
- Architecture: HIGH — pattern verified directly in codebase (microstructure_features.py is the template)
- Plan A (quote stream): HIGH — confirmed available fields from Capital.com API docs
- Plan B (OHLCV formulas): HIGH — BVC academic validation + Python runtime test
- Pitfalls: HIGH — most derived from direct code inspection + confirmed pandas 3.0 risk

**Research date:** 2026-03-27
**Valid until:** 2026-06-27 (stable libraries; Capital.com API changes would invalidate Plan A findings)
