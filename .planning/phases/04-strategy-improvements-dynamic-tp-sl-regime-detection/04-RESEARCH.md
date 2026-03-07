# Phase 4: Strategy Improvements -- Dynamic TP/SL & Regime Detection - Research

**Researched:** 2026-03-07
**Domain:** Trading strategy adaptation, volatility-based risk management, market regime detection
**Confidence:** HIGH

## Summary

Phase 4 transforms the GoldBot trading system from static, fixed-parameter trading to dynamic, market-adaptive trading. The codebase currently uses hardcoded TP/SL pips in two distinct contexts: (1) label generation during training (`LabelGenerator` with `tp_pips=50`, `sl_pips=30` defaults), and (2) live trade execution (where `EnsemblePredictor._calculate_sl_tp()` already uses ATR-based SL/TP with `atr * 1.5` for SL and `sl_distance * risk_reward_ratio` for TP). The training pipeline's `Backtester` also uses fixed TP/SL pips for performance evaluation.

The key insight is that the live execution path already has ATR-based TP/SL in the ensemble predictor, but the training label generation and backtesting evaluation are still using fixed pips. This creates a mismatch: the model learns labels defined by fixed barriers but trades with dynamic ones. Phase 4 must align these, add regime detection, and make position sizing ATR-aware.

**Primary recommendation:** Build a `RegimeDetector` class that classifies market state using ADX + ATR + Bollinger Band Width (all already computed), then create a `DynamicLabelGenerator` that uses per-candle ATR for triple barrier labels, and integrate regime-aware parameter selection across the strategy pipeline.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| STRAT-01 | Dynamic TP/SL based on ATR instead of fixed 50/30 pips | ATR already computed as `atr_14` in `indicators.py`. `LabelGenerator` needs ATR-based distances. `EnsemblePredictor._calculate_sl_tp()` already does ATR-based SL/TP for live trades. `Backtester` needs matching dynamic evaluation. |
| STRAT-02 | ATR-based position sizing adapts to market volatility | `PositionSizer` already calculates from SL distance. When SL is ATR-based, position size automatically scales. Need explicit ATR normalization to avoid over-sizing in low-vol and under-sizing in high-vol. |
| STRAT-03 | Regime detection classifies market as trending/ranging/volatile | ADX (`adx_14`), ATR (`atr_14`), BB width (`bb_bandwidth`) already computed. `GoldSpecificFeatures` has `current_volatility`, `is_high_volatility`. Need to combine these into a discrete regime classifier. |
| STRAT-04 | Strategy parameters differ per detected regime | `StrategyManager.evaluate()` and `TradeScorer.score()` use fixed thresholds. Need regime-aware parameter lookup: different ATR multipliers, confidence thresholds, and score weights per regime. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | existing | ATR rolling calculations, regime feature computation | Already in use throughout codebase |
| numpy | existing | Vectorized regime classification, ATR computations | Already in use throughout codebase |
| pandas-ta | existing | ATR, ADX, Bollinger Bands already computed via `indicators.py` | Already in `market_data/indicators.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | `RegimeState` and `DynamicParams` data structures | Regime parameter containers |
| enum | stdlib | `MarketRegime` enum (TRENDING, RANGING, VOLATILE) | Regime type classification |
| logging | stdlib | Regime change logging, parameter adaptation logging | Observability |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Rule-based regime detection | Hidden Markov Model (hmmlearn) | HMM is more sophisticated but adds dependency, harder to debug, overkill for 3 states with clear indicator-based rules |
| Fixed ATR multipliers per regime | Optimized multipliers via backtesting | Optimization is Phase 5 territory; start with sensible defaults, validate later |
| Custom ATR calculation | pandas-ta ATR | pandas-ta already computes ATR in `indicators.py`; no reason to duplicate |

**Installation:**
No new dependencies required. All needed libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
strategy/
    regime_detector.py       # NEW: MarketRegime enum + RegimeDetector class
    regime_params.py         # NEW: Per-regime parameter lookup tables
    entry_calculator.py      # MODIFY: Use regime-aware ATR multipliers
    strategy_manager.py      # MODIFY: Pass regime to scorer, adjust thresholds
    trade_scorer.py          # MODIFY: Regime-aware scoring weights
ai_engine/
    training/
        label_generator.py   # MODIFY: ATR-based dynamic TP/SL per candle
        backtester.py        # MODIFY: ATR-based TP/SL evaluation
        pipeline.py          # MODIFY: Pass ATR data to label generator
risk/
    position_sizing.py       # MODIFY: ATR-normalized position sizing
shared/
    constants.py             # MODIFY: Add regime-specific default parameters
```

### Pattern 1: ATR-Based Dynamic Label Generation
**What:** Replace fixed `tp_pips`/`sl_pips` in `LabelGenerator` with per-candle ATR-scaled distances
**When to use:** During training pipeline (Step 3: Generate labels)
**Key design decisions:**
- The `LabelGenerator.__init__()` currently takes `tp_pips` and `sl_pips` as fixed floats
- New approach: pass ATR multipliers instead (e.g., `tp_atr_mult=2.0`, `sl_atr_mult=1.5`)
- The `generate_labels()` method receives the DataFrame which already has `atr_14` column
- Per-candle: `tp_dist = atr_14[i] * tp_atr_mult`, `sl_dist = atr_14[i] * sl_atr_mult`
- Costs still deducted from effective distances (same as current logic)
- Fallback: if ATR is NaN (warmup period), use a sensible default (median ATR of available data)

**Example:**
```python
# In DynamicLabelGenerator (extends or replaces LabelGenerator)
def generate_labels(self, df: pd.DataFrame) -> pd.Series:
    atr = df["atr_14"].values
    # Handle NaN ATR in warmup period
    median_atr = np.nanmedian(atr)
    atr = np.where(np.isnan(atr), median_atr, atr)

    # Per-candle TP/SL distances
    tp_dist = atr * self.tp_atr_multiplier  # e.g., 2.0x ATR
    sl_dist = atr * self.sl_atr_multiplier  # e.g., 1.5x ATR

    # Subtract costs (same as current)
    tp_dist_effective = tp_dist + self.total_cost  # TP further
    sl_dist_effective = sl_dist - self.total_cost  # SL closer
    sl_dist_effective = np.maximum(sl_dist_effective, self.pip_size)

    # Vectorized labeling with per-candle distances
    labels = self._vectorized_labeling_dynamic(
        close, high, low, n, tp_dist_effective, sl_dist_effective
    )
    return pd.Series(labels, index=df.index, name="label")
```

### Pattern 2: Rule-Based Regime Detection
**What:** Classify market into TRENDING, RANGING, or VOLATILE using ADX + ATR ratio + BB width
**When to use:** At prediction time (before signal evaluation) and during backtesting

**Classification rules (based on standard technical analysis):**
- **TRENDING:** ADX > 25 AND (DI+ or DI- dominant) -- strong directional movement
- **VOLATILE:** ATR > 1.5x rolling average ATR AND BB width expanding -- high volatility, no clear direction
- **RANGING:** ADX < 20 AND BB width contracting -- low volatility, mean-reverting

**Example:**
```python
class MarketRegime(enum.Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"

class RegimeDetector:
    def __init__(
        self,
        adx_trend_threshold: float = 25.0,
        adx_range_threshold: float = 20.0,
        atr_volatile_ratio: float = 1.5,
        lookback_periods: int = 20,
    ):
        ...

    def detect(self, df: pd.DataFrame) -> MarketRegime:
        """Classify current market regime from latest indicator values."""
        last = df.iloc[-1]
        adx = last.get("adx", last.get("adx_14", 0))
        atr = last.get("atr_14", 0)
        atr_avg = df["atr_14"].tail(self.lookback_periods).mean()
        atr_ratio = atr / atr_avg if atr_avg > 0 else 1.0

        # Check volatile first (takes priority)
        if atr_ratio > self.atr_volatile_ratio:
            return MarketRegime.VOLATILE

        # Check trending
        if adx > self.adx_trend_threshold:
            return MarketRegime.TRENDING

        # Default: ranging
        if adx < self.adx_range_threshold:
            return MarketRegime.RANGING

        # Ambiguous zone (20 <= ADX <= 25): use ATR ratio as tiebreaker
        return MarketRegime.RANGING if atr_ratio < 1.0 else MarketRegime.TRENDING
```

### Pattern 3: Regime-Specific Parameter Tables
**What:** Lookup table mapping each regime to strategy parameters
**When to use:** After regime detection, before signal evaluation and trade execution

```python
REGIME_PARAMS = {
    MarketRegime.TRENDING: {
        "tp_atr_multiplier": 2.5,    # Let winners run in trends
        "sl_atr_multiplier": 1.5,    # Standard SL
        "min_confidence": 0.65,      # Slightly lower bar (trend is friend)
        "min_trade_score": 55,       # More willing to trade
        "rr_min": 1.5,              # Standard R:R
    },
    MarketRegime.RANGING: {
        "tp_atr_multiplier": 1.5,    # Tighter TP (mean reversion)
        "sl_atr_multiplier": 1.0,    # Tighter SL
        "min_confidence": 0.75,      # Higher bar (choppy markets)
        "min_trade_score": 65,       # More selective
        "rr_min": 1.2,              # Accept lower R:R for higher probability
    },
    MarketRegime.VOLATILE: {
        "tp_atr_multiplier": 3.0,    # Wide TP (big moves possible)
        "sl_atr_multiplier": 2.0,    # Wide SL (avoid noise stops)
        "min_confidence": 0.80,      # Very high bar
        "min_trade_score": 70,       # Very selective
        "rr_min": 1.5,              # Standard R:R
    },
}
```

### Pattern 4: ATR-Normalized Position Sizing
**What:** Scale position size inversely with ATR to maintain consistent dollar risk
**When to use:** In risk management, after SL is calculated

```python
# Current: lot_size = risk_amount / sl_distance
# This ALREADY adapts to ATR-based SL implicitly.
# When ATR is high -> SL is wider -> lot_size is smaller (less risk per point)
# When ATR is low -> SL is tighter -> lot_size is larger (more risk per point)
#
# The key insight: with ATR-based SL, PositionSizer already does ATR-normalized
# sizing. The improvement is making this explicit and adding a max ATR guard.

def calculate_with_atr_guard(
    self, equity: float, entry_price: float, stop_loss: float,
    atr: float, max_atr_for_trading: float = 5.0
) -> float:
    """Position sizing with ATR guard to skip extreme volatility."""
    if atr > max_atr_for_trading:
        logger.warning("ATR %.2f exceeds max %.2f -- reducing position", atr, max_atr_for_trading)
        return self.min_lot_size
    return self.calculate(equity, entry_price, stop_loss)
```

### Anti-Patterns to Avoid
- **Optimizing regime thresholds during training:** This is curve-fitting. Use sensible defaults from technical analysis literature (ADX 25 for trending is widely established). Optimization belongs in Phase 5 backtesting.
- **Using too many regimes:** Three states (TRENDING/RANGING/VOLATILE) are sufficient. Adding sub-states (bull-trend vs bear-trend, low-vol-range vs high-vol-range) creates a combinatorial explosion of parameters with insufficient data per bucket.
- **Regime detection on training labels:** The regime detector should classify based on indicator values, not label outcomes. Labels are derived from price movement; regime is derived from indicator state. These are independent.
- **Different models per regime:** Training separate models per regime splits the already limited dataset. Instead, use one model but adjust trading parameters (TP/SL, confidence thresholds) per regime.
- **Changing ATR period per regime:** Keep ATR-14 consistent. Switching between ATR-7 and ATR-20 based on regime adds complexity without clear benefit and breaks feature consistency.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ATR calculation | Custom true range + rolling mean | `pandas-ta.atr()` in `indicators.py` | Already computed as `atr_14`, battle-tested |
| ADX calculation | Custom directional index math | `pandas-ta.adx()` in `indicators.py` | Already computed as `adx`, `di_plus`, `di_minus` |
| Bollinger Bands width | Custom BB calculation | `pandas-ta.bbands()` in `indicators.py` | Already computed as `bb_bandwidth` |
| Position sizing math | New sizing algorithm | Existing `PositionSizer` with ATR-based SL inputs | SL-distance-based sizing already normalizes for volatility |

**Key insight:** The indicators needed for all four requirements (ATR, ADX, BB width) are already computed in `market_data/indicators.py`. The regime detector is a thin classification layer on top of existing indicators, not a new calculation engine.

## Common Pitfalls

### Pitfall 1: Training-Execution Mismatch
**What goes wrong:** Training labels use fixed TP/SL, but live execution uses ATR-based TP/SL. The model learns patterns for a different risk profile than it trades with.
**Why it happens:** Label generation and live execution were built independently.
**How to avoid:** Update `LabelGenerator` to use ATR-based distances in parallel with live execution. The `atr_14` column is already in the DataFrame when features are computed (Step 2 of pipeline) before labels are generated (Step 3).
**Warning signs:** Model accuracy degrades relative to training metrics; win rate in live trading differs significantly from backtest win rate.

### Pitfall 2: ATR NaN During Warmup
**What goes wrong:** The first ~14 candles have NaN for `atr_14` (ATR-14 needs 14 periods). Using NaN for TP/SL distances produces NaN labels.
**Why it happens:** Technical indicators need a warmup period.
**How to avoid:** In the label generator, fill NaN ATR values with the median ATR of the non-NaN portion. The pipeline already removes 200 warmup candles (Step 4), but labels are generated BEFORE warmup removal (Step 3), so ATR NaN handling must be in the label generator itself.
**Warning signs:** NaN or all-zero labels in the first N rows of training data.

### Pitfall 3: ATR at Zero or Near-Zero
**What goes wrong:** In synthetic data or very calm periods, ATR can be extremely small, causing TP/SL to be unrealistically tight (< spread cost).
**Why it happens:** ATR reflects true range; in flat markets, it approaches zero.
**How to avoid:** Set minimum TP/SL floor: `tp_dist = max(atr * multiplier, min_tp_pips * pip_size)`. For Gold, a reasonable minimum is 5 pips ($0.05).
**Warning signs:** Labels are almost all HOLD because TP/SL are inside spread cost.

### Pitfall 4: Regime Flickering
**What goes wrong:** Regime changes every candle (TRENDING -> RANGING -> TRENDING -> ...), causing rapid parameter switching.
**Why it happens:** ADX and ATR cross thresholds frequently when near boundary values.
**How to avoid:** Use a smoothed regime with hysteresis. Require N consecutive candles (e.g., 3-5) of the same regime before switching. Or use the rolling average of ADX/ATR ratio over last N candles instead of instantaneous values.
**Warning signs:** Log shows regime changing every few ticks; trade parameters oscillate.

### Pitfall 5: Over-Parameterization
**What goes wrong:** Each regime has 5+ parameters, creating 15+ tunable values with no data to optimize them.
**Why it happens:** Temptation to fine-tune every aspect per regime.
**How to avoid:** Start with conservative defaults from technical analysis best practices. Only tune 2-3 parameters per regime (ATR multipliers for TP/SL, confidence threshold). Let Phase 5 backtesting validate.
**Warning signs:** Spending more time tuning parameters than testing outcomes.

### Pitfall 6: Backtester Inconsistency
**What goes wrong:** `Backtester` in `backtester.py` evaluates trades with fixed `tp_pips`/`sl_pips` while labels and live execution use ATR-based values. Performance metrics become meaningless.
**Why it happens:** Backtester was built for fixed TP/SL; updating labels without updating backtester creates inconsistency.
**How to avoid:** Update `Backtester.run_simple()` and `_close_position()` to accept per-trade TP/SL (from ATR at entry time) rather than using class-level fixed values.
**Warning signs:** Backtest win rate looks great but live trading underperforms (or vice versa).

## Code Examples

### Current Flow: Where TP/SL Are Used

**1. Training labels (`label_generator.py` line 97-98):**
```python
tp_dist = self.tp_pips * self.pip_size   # Fixed: 50 * 0.01 = 0.50
sl_dist = self.sl_pips * self.pip_size   # Fixed: 30 * 0.01 = 0.30
```

**2. Live prediction SL/TP (`ensemble.py` line 732-758):**
```python
# ALREADY ATR-BASED!
atr = float(df["atr_14"].iloc[-1])
sl_distance = atr * 1.5
tp_distance = sl_distance * self.risk_reward_ratio  # 2.0
```

**3. Entry calculator (`entry_calculator.py` line 11-37):**
```python
# ALREADY ATR-BASED! Uses SL_ATR_MULTIPLIER=1.5 and TP_ATR_MULTIPLIER=2.0
sl = entry - (sl_multiplier * atr)  # from constants
tp = entry + (tp_multiplier * atr)  # from constants
```

**4. Backtester evaluation (`backtester.py` line 181-184):**
```python
net_tp = self.tp_pips - self.total_cost_pips   # Fixed pips
net_sl = self.sl_pips + self.total_cost_pips   # Fixed pips
pips_per_trade = np.where(wins, net_tp, -net_sl)
```

**5. Training script defaults (`train_models.py` line 133-134):**
```python
parser.add_argument("--tp-pips", type=float, default=1500.0)
parser.add_argument("--sl-pips", type=float, default=800.0)
```

### Key Indicator Values Already Available

From `indicators.py`, these are already computed on every DataFrame:
- `atr_14` -- Average True Range (14-period)
- `adx` -- Average Directional Index
- `di_plus`, `di_minus` -- Directional Indicators
- `bb_bandwidth` -- Bollinger Band width
- `bb_percent` -- BB %B (position within bands)

From `gold_specific.py`, these derived features exist:
- `current_volatility` -- ATR/Close * 100 (normalized)
- `volatility_change` -- ATR ratio vs 60 candles ago
- `is_high_volatility` -- Binary flag (ATR > rolling mean)

From `technical_features.py`:
- `adx_trending` -- Binary flag (ADX > 25)
- `bb_squeeze` -- Binary flag (BB width in bottom 10%)

### Integration Points

**StrategyManager.evaluate()** (line 90-101):
```python
# Currently extracts ADX and ATR for scoring
adx = float(last.get("adx", 0) or 0) or None
atr = float(last.get("atr_14", 0) or 0) or None
# ADD: regime = self.regime_detector.detect(df)
# ADD: params = REGIME_PARAMS[regime]
```

**TradeScorer.score()** (line 67-76):
```python
# Currently uses fixed ADX thresholds
if adx >= 40: trend_score = 15.0
elif adx >= 25: trend_score = 10.0
# MODIFY: Use regime-aware scoring weights
```

**PositionSizer.calculate()** (line 25-53):
```python
# Currently: lot_size = risk_amount / sl_distance
# When sl_distance is ATR-based, sizing ALREADY adapts
# ADD: ATR guard for extreme volatility
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed TP/SL pips in labels | ATR-based dynamic TP/SL | This phase | Labels reflect actual market volatility at each candle |
| No regime awareness | 3-state regime detector | This phase | Strategy parameters adapt to market conditions |
| Fixed position sizing | ATR-normalized sizing | This phase | Consistent risk per trade regardless of volatility |
| Prediction uses ATR SL/TP, training uses fixed | Aligned ATR-based across training and execution | This phase | Eliminates training-execution mismatch |

**Important existing state:**
- The `EnsemblePredictor._calculate_sl_tp()` ALREADY uses ATR for live SL/TP (line 732-758)
- The `entry_calculator.py` ALREADY uses ATR multipliers from constants
- The `TradeScorer` ALREADY has volatility scoring (ATR ratio check, line 85-95)
- The `GoldSpecificFeatures` ALREADY has volatility features

This means Phase 4 is largely about:
1. Bringing training labels in line with live execution (ATR-based)
2. Formalizing regime detection from existing indicator features
3. Adding parameter lookup per regime
4. Updating backtester to match

## Open Questions

1. **ATR Multiplier Defaults for Gold**
   - What we know: Live execution uses 1.5x ATR for SL, 2.0x RR ratio. `entry_calculator.py` uses `SL_ATR_MULTIPLIER=1.5`, `TP_ATR_MULTIPLIER=2.0` from constants. These are reasonable starting points.
   - What's unclear: Optimal multipliers per regime. Should trending TP be 2.5x or 3.0x ATR?
   - Recommendation: Use the values above as defaults. Regime adjustments: trending TP=2.5, ranging TP=1.5, volatile TP=3.0. Validate in Phase 5 backtesting.

2. **Label Generator: Replace or Extend?**
   - What we know: `LabelGenerator` is used by `pipeline.py` step 3, and its `get_params()` is stored in version metadata. Tests reference it.
   - What's unclear: Should we replace `LabelGenerator` in-place or create a `DynamicLabelGenerator` subclass?
   - Recommendation: Modify `LabelGenerator` in-place with a `use_dynamic_atr: bool` flag (default True). When True, use ATR columns from the DataFrame. When False, fall back to fixed pips (backward compatibility for tests). This avoids breaking existing test infrastructure while enabling the new behavior.

3. **Regime Detection: Per-Candle or Per-Tick?**
   - What we know: In live trading, `_trading_tick()` runs every 60 seconds. Regime doesn't change that fast.
   - What's unclear: Should regime be re-evaluated every tick or cached?
   - Recommendation: Re-evaluate on each tick (it's cheap -- one row lookup) but use hysteresis (require 3+ candles confirmation) to avoid flickering.

4. **Backtester Update Scope**
   - What we know: `Backtester` is used in `walk_forward.py` for per-window evaluation. It uses fixed TP/SL.
   - What's unclear: How deeply should the backtester be updated? Full ATR-based per-trade evaluation or simplified?
   - Recommendation: Update `run_simple()` to accept per-trade TP/SL arrays. The walk-forward validation already has access to the DataFrame with ATR values. Pass ATR-scaled TP/SL per prediction for realistic evaluation.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** - Direct reading of all key files: `label_generator.py`, `ensemble.py`, `entry_calculator.py`, `strategy_manager.py`, `trade_scorer.py`, `position_sizing.py`, `risk_manager.py`, `indicators.py`, `pipeline.py`, `backtester.py`, `trading_loop.py`, `signal_generator.py`, `technical_features.py`, `gold_specific.py`, `constants.py`, `settings.py`, `train_models.py`, `trainer.py`
- **Project state** - `STATE.md`, `REQUIREMENTS.md`, `ROADMAP.md` for phase scope and constraints

### Secondary (MEDIUM confidence)
- **ATR multiplier conventions** - 1.5x ATR for SL and 2.0-3.0x ATR for TP are widely established in technical analysis for Gold trading (Wilder's original ATR recommendations, adapted for modern CFD trading)
- **ADX thresholds** - ADX > 25 for trending, ADX < 20 for ranging are standard interpretations from Welles Wilder's original ADX methodology

### Tertiary (LOW confidence)
- **Regime-specific parameter values** - The exact multiplier differences per regime (e.g., 2.5 vs 1.5 vs 3.0 for TP) are educated defaults, not empirically validated for this specific Gold 5m setup. Phase 5 backtesting should validate these.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies needed; all indicators already computed
- Architecture: HIGH - Clear modification points identified in existing code; existing ATR usage in ensemble.py provides a tested pattern
- Pitfalls: HIGH - Training-execution mismatch is clearly visible in code; ATR NaN handling is a known issue in any ATR-based system
- Regime parameters: MEDIUM - Default values are standard TA conventions but optimal Gold-5m-specific values need backtesting validation

**Research date:** 2026-03-07
**Valid until:** 2026-04-07 (stable domain; no dependency version concerns)
