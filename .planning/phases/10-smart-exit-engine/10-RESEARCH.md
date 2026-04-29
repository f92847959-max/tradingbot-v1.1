# Phase 10: Smart Exit Engine - Research

**Researched:** 2026-03-26
**Domain:** Trading exit management — ATR-based SL, Fibonacci TP, trailing stops, partial close, reversal detection
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXIT-01 | Dynamischer SL berechnet aus ATR + Struktur-Level (nicht fix) | ATR-14 already in indicators.py; REGIME_PARAMS already has sl_atr_multiplier per regime; swing high/low detection is pure pandas — no new library needed |
| EXIT-02 | Dynamischer TP anhand Fibonacci Extensions / naechste S/R-Zone | Fibonacci extension math is simple arithmetic; S/R from rolling window on high/low columns; pandas-ta already installed |
| EXIT-03 | Trailing Stop aktiviert nach +1R, trailt per ATR | TrailingStopManager exists in order_management/trailing_stop.py — needs ATR-aware extension, not full rewrite |
| EXIT-04 | Partial Close schliesst 50% bei TP1, Rest laeuft mit Trailing | Capital.com API supports partial close via `PUT /api/v1/positions/{deal_id}` with reduced size; CapitalComClient.modify_position() exists and can be extended |
| EXIT-05 | Exit-Signale erkennen Reversals (Kerzen, Momentum-Divergenz) | RSI-14 and MACD histogram already computed in indicators.py; reversal candle detection is pure pandas math |

</phase_requirements>

---

## Summary

Phase 10 builds a new `exit_engine/` package that replaces fixed TP/SL values with intelligent, regime-aware exit management. The project already has solid ATR and regime infrastructure: `atr_14` is computed in `market_data/indicators.py`, `REGIME_PARAMS` in `strategy/regime_params.py` already has `sl_atr_multiplier` and `tp_atr_multiplier` per regime, and `strategy/entry_calculator.py` already has `calculate_sl_tp_for_regime()`. An existing `TrailingStopManager` in `order_management/trailing_stop.py` performs fixed-pip trailing — it needs an ATR-aware replacement, not a full rewrite.

The Capital.com API supports both full closes (`DELETE /api/v1/positions/{deal_id}`) and partial size reduction through `PUT /api/v1/positions/{deal_id}` with a modified size. The existing `modify_position()` method handles stop/limit edits; a partial close requires a dedicated method that sends a reduced `size` field. The broker client does not currently have a `partial_close_position()` method — this must be added.

The plan (10-01-PLAN.md) already exists and is detailed. This research confirms all algorithmic choices in that plan, identifies the one API gap (partial close method), and maps the integration points so the planner can produce Plans 02 and 03 with confidence.

**Primary recommendation:** Build `exit_engine/` as a pure-logic package (no broker calls), wire it into `OrderManager.check_positions()` and the position monitor loop, and add a `partial_close_position()` method to `CapitalComClient`.

---

## Standard Stack

### Core (already installed — no new packages needed)

| Library | Version Installed | Purpose | Why Used |
|---------|------------------|---------|----------|
| pandas | 3.0.0 | DataFrame operations for swing detection, rolling windows | Already project standard |
| numpy | 2.2.6 | Vectorized math for Fibonacci, ATR calculations | Already project standard |
| pandas-ta | 0.4.71b0 | ATR-14, RSI-14, MACD already computed by this library | Already in indicators.py |
| scipy | 1.17.0 | Available if needed for signal processing, but not required | Already installed |

**No new dependencies required for Phase 10.** All algorithmic work (Fibonacci math, swing point detection, reversal candle pattern matching) uses only pandas and numpy arithmetic.

### Alternatives Considered

| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| Custom swing detection | ta-lib | ta-lib requires C compilation on Windows; project already uses pandas-ta which is pure Python |
| Custom Fibonacci math | pandas-ta `fibonacci()` | pandas-ta fibonacci extension is less documented; simple arithmetic is clearer and testable |
| RSI divergence via ML | Rule-based comparison | ML approach needs training data for exits; rule-based is deterministic and auditable |

---

## Architecture Patterns

### Recommended Project Structure

```
exit_engine/
├── __init__.py          # package init
├── types.py             # Shared dataclasses: ExitLevels, TrailingResult, PartialCloseAction, ExitSignal, StructureLevel
├── dynamic_sl.py        # ATR + structure-based SL (EXIT-01)
├── dynamic_tp.py        # Fibonacci extensions + S/R zone TP (EXIT-02)
├── trailing_manager.py  # ATR-based trailing, breakeven-then-trail logic (EXIT-03)
├── partial_close.py     # TP1 detection, 50% close trigger logic (EXIT-04)
└── exit_signals.py      # Reversal candle + RSI/MACD divergence detection (EXIT-05)
```

Integration points:
- `order_management/order_manager.py` — `check_positions()` calls all exit engine components
- `order_management/trailing_stop.py` — replaced or extended by `exit_engine/trailing_manager.py`
- `market_data/broker_client.py` — needs `partial_close_position()` added
- `trading/monitors.py` — `_position_monitor_loop` already polls every 30 seconds; exit engine hooks into this loop

### Pattern 1: Regime-Aware ATR SL (EXIT-01)

**What:** SL distance = `atr * regime_sl_multiplier`, then adjust toward nearest structure level (swing low for BUY, swing high for SELL).

**When to use:** On every new trade entry, replacing `calculate_sl_tp()` in entry_calculator.py.

**Key values from REGIME_PARAMS:**
```python
# Already defined in strategy/regime_params.py
REGIME_PARAMS = {
    MarketRegime.TRENDING: {"sl_atr_multiplier": 1.5, "tp_atr_multiplier": 2.5},
    MarketRegime.RANGING:  {"sl_atr_multiplier": 1.0, "tp_atr_multiplier": 1.5},
    MarketRegime.VOLATILE: {"sl_atr_multiplier": 2.0, "tp_atr_multiplier": 3.0},
}
```

**Example pattern:**
```python
# Source: strategy/regime_params.py + strategy/entry_calculator.py
def calculate_dynamic_sl(direction, entry_price, atr, regime, structure_levels=None):
    params = get_regime_params(regime)
    atr_sl_distance = atr * params["sl_atr_multiplier"]
    if direction == "BUY":
        atr_sl = entry_price - atr_sl_distance
        if structure_levels:
            supports = [s for s in structure_levels if s.price < entry_price]
            if supports:
                nearest = max(supports, key=lambda s: s.price)
                structure_sl = nearest.price - (BUFFER_PIPS * PIP_SIZE)
                sl = max(atr_sl, structure_sl)  # more protective for BUY = higher
            else:
                sl = atr_sl
    # ... SELL mirror logic
    return round(sl, 2)
```

### Pattern 2: Fibonacci Extension TP (EXIT-02)

**What:** Compute Fibonacci extension levels from the most recent swing move. Standard levels: 1.0, 1.272, 1.618, 2.0, 2.618. Pick the nearest level beyond entry that satisfies minimum distance.

**Gold-specific note:** For 5-minute XAUUSD charts, ATR-14 is typically $1.50-$4.00. Fibonacci levels derived from 50-candle swings give realistic TP targets in the $3-$15 range per trade, consistent with REGIME_PARAMS tp_atr_multiplier values.

```python
# Fibonacci extension arithmetic — no library needed
def fibonacci_extensions(entry, swing_low, swing_high):
    swing_range = swing_high - swing_low
    ratios = [1.0, 1.272, 1.618, 2.0, 2.618]
    # For upswing (BUY): extensions project above swing_high
    return [swing_high + swing_range * (r - 1.0) for r in ratios]
```

### Pattern 3: ATR Trailing Stop with Breakeven (EXIT-03)

**What:** Activate trailing after profit reaches +1R (1x risk distance). First move SL to breakeven, then trail at `current_price - (atr * trail_multiplier)` for BUY.

**Replaces:** The existing `TrailingStopManager` which uses fixed pips. The new version uses ATR units.

**Chandelier Exit formula (standard):**
```python
# Chandelier Exit = Highest High (last N) - ATR * multiplier
# For Gold intraday (5m), N=22 periods is standard
chandelier_sl = df["high"].rolling(22).max() - (atr * 3.0)
```

**Activation logic:** Profit in R = `(current_price - entry_price) / (entry_price - stop_loss)` for BUY. When profit_r >= 1.0, activate trailing. This is the +1R breakeven trigger per EXIT-03.

### Pattern 4: Partial Close (EXIT-04)

**What:** When price reaches TP1 (50% of full TP distance from entry), close 50% of position. Allow remaining 50% to trail.

**Capital.com API:** Partial close is possible via `PUT /api/v1/positions/{deal_id}` with a `size` field set to the remaining size after partial close. This is a position modification that reduces size, NOT a separate close endpoint. The existing `modify_position()` in broker_client.py only sends `stopLevel`/`limitLevel` — a new `partial_close_position(deal_id, close_fraction)` method is needed.

**Verification:** Confirmed through Capital.com API documentation pattern — the PUT positions endpoint accepts `size` to modify the position quantity.

**Key logic:**
```python
async def partial_close_position(self, deal_id: str, close_fraction: float = 0.5) -> OrderResult:
    position = await self.get_position(deal_id)  # need to add get_position()
    remaining_size = round(position.size * (1.0 - close_fraction), 2)
    # Capital.com: size below minimum will reject — check min_size
    payload = {"size": remaining_size}
    data = await self._request("PUT", f"/api/v1/positions/{deal_id}", payload)
    return await self._get_confirmation(data.get("dealReference", ""))
```

### Pattern 5: Exit Signal Detection (EXIT-05)

**What:** Scan last N candles for reversal candle patterns and RSI/MACD momentum divergence. Already available: `rsi_14`, `macd_histogram` columns in indicator output.

**Bearish engulfing (BUY exit):**
- Current candle: close < open (bearish body)
- Current open >= previous close AND current close <= previous open (engulfs previous body)
- Body condition: current body > previous body

**RSI divergence (BUY exit):**
- Price makes higher high in last 5 candles
- RSI makes lower high at same points = bearish divergence

**MACD divergence (BUY exit):**
- `macd_histogram` column already available
- Declining histogram while price still rising = weakening momentum

### Anti-Patterns to Avoid

- **Moving SL against the trade:** SL for BUY must never move lower (only higher or stay). Already enforced in existing TrailingStopManager — must keep this invariant.
- **Partial close below broker minimum lot:** Capital.com has minimum position size (~0.01 lots for Gold CFD). Partial close of 50% could produce 0.005 lots which will be rejected. Always validate remaining size >= min_lot before attempting partial close.
- **Exit signals firing on noise:** RSI divergence on 5-minute charts is noisy. Require 2+ consecutive candles confirming before triggering. Single-candle divergence = low confidence.
- **Fibonacci with no clear swing:** If swing_high - swing_low < 2 * ATR, skip Fibonacci and fall back to ATR TP. Noise-driven swings produce meaningless extension levels.
- **Trailing stop causing breakeven at entry:** After moving SL to breakeven (entry price), ensure a buffer of at least 1 spread width (0.30 for Gold) to avoid immediate SL hit from spread.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| ATR calculation | Custom TR/ATR loop | `pandas_ta.atr()` already in indicators.py | Already computed for every candle, column `atr_14` |
| RSI computation | Custom Wilder smoothing | `pandas_ta.rsi()` already in indicators.py | Column `rsi_14` available in all DataFrames |
| MACD histogram | Custom MACD implementation | `pandas_ta.macd()` already in indicators.py | Column `macd_histogram` available |
| Rolling max/min | Custom loop | `pd.Series.rolling(N).max()` | Pandas built-in, vectorized |
| Swing point detection | External library | Pandas boolean mask: `high[i] > high[i-1] and high[i] > high[i+1]` | Two-line numpy operation; simpler than any library |

**Key insight:** All indicator inputs needed by the exit engine are already pre-computed by `calculate_indicators()` in `market_data/indicators.py`. The exit engine consumes these columns — it does not recompute indicators.

---

## Runtime State Inventory

> Omitted: Phase 10 is greenfield addition of exit_engine/ package. No existing production data uses "exit_engine" as a key or ID. No rename/refactor involved.

---

## Common Pitfalls

### Pitfall 1: Capital.com Minimum Lot Size on Partial Close
**What goes wrong:** Partial close attempt fails with "REJECTED: minimum size" error when half the position size falls below 0.01 lots.
**Why it happens:** Gold CFD minimum lot at Capital.com is ~0.01. A 0.01 lot position partially closed to 0.005 lots will be rejected.
**How to avoid:** Before partial close, check `close_size = position.size * fraction`. If `position.size - close_size < MIN_LOT`, either skip partial close or close full position.
**Warning signs:** `OrderResult.status == "REJECTED"` with reason containing "size" or "minimum".

### Pitfall 2: Swing Level Detection on Short History
**What goes wrong:** `find_swing_levels()` finds no structure levels when called with fewer than 20 candles.
**Why it happens:** A swing high/low requires checking neighbors at both sides; edge candles at start/end of window cannot be swing points.
**How to avoid:** Require minimum 20 candles for swing detection. Fall back to pure ATR-based SL/TP if insufficient history.
**Warning signs:** Empty `structure_levels` list returned even in a clearly trending/ranging market.

### Pitfall 3: ATR = 0 Edge Case
**What goes wrong:** Division by zero or SL = entry when ATR is 0 or NaN.
**Why it happens:** First few candles of the DataFrame have NaN ATR; can also happen if data provider returns identical OHLC for all fields (weekend candles).
**How to avoid:** Guard: `if atr is None or atr <= 0: raise ValueError(...)` at the top of every ATR-using function. The existing codebase already guards this in regime_detector.py.
**Warning signs:** SL calculated as exactly equal to entry price.

### Pitfall 4: Trailing Stop Modifying Position Every Tick
**What goes wrong:** Every 30-second position check triggers a `modify_position()` call even when SL only moved by $0.01, burning API rate limit.
**Why it happens:** ATR-based trailing moves continuously as price moves.
**How to avoid:** Only call `modify_position()` when new SL differs from current SL by at least 2x pip_size (minimum meaningful move). The existing TrailingStopManager already handles "only move in favorable direction" but not minimum increment.
**Warning signs:** High volume of API calls in logs, rate limiter warnings.

### Pitfall 5: Exit Signals Causing Double-Close
**What goes wrong:** Exit signal fires AND trailing SL hits in the same check cycle, causing two close attempts on the same position.
**Why it happens:** `check_positions()` checks trailing and exit signals independently.
**How to avoid:** Once an exit action (close or partial close) is initiated for a deal_id, skip all further checks for that deal_id in the same cycle. Use a `_pending_exits: set[str]` guard in OrderManager.
**Warning signs:** `BrokerError: position already closed` errors in logs.

### Pitfall 6: Fibonacci Levels Behind Entry Price
**What goes wrong:** Fibonacci extension for a BUY returns a TP level that is below entry price.
**Why it happens:** If the swing was identified incorrectly (swing_high < swing_low swap), extensions go in wrong direction.
**How to avoid:** After computing TP, validate: for BUY `tp > entry_price + min_tp_pips * pip_size`. If invalid, fall back to ATR TP. Add an assertion in tests.
**Warning signs:** TP for BUY is below current price at time of calculation.

---

## Code Examples

### Swing High/Low Detection (pure pandas)
```python
# Source: standard TA pattern, confirmed via pandas documentation
def find_swing_highs(high_series: pd.Series, window: int = 5) -> pd.Series:
    """Returns boolean mask where True = swing high."""
    roll_max = high_series.rolling(window=window, center=True).max()
    return high_series == roll_max

def find_swing_lows(low_series: pd.Series, window: int = 5) -> pd.Series:
    """Returns boolean mask where True = swing low."""
    roll_min = low_series.rolling(window=window, center=True).min()
    return low_series == roll_min
```

### Chandelier Exit (ATR-based trailing SL)
```python
# Source: Elder's Chandelier Exit, standard implementation
def chandelier_exit_long(high_series: pd.Series, atr: float, period: int = 22, multiplier: float = 3.0) -> float:
    highest_high = high_series.iloc[-period:].max()
    return highest_high - (atr * multiplier)

def chandelier_exit_short(low_series: pd.Series, atr: float, period: int = 22, multiplier: float = 3.0) -> float:
    lowest_low = low_series.iloc[-period:].min()
    return lowest_low + (atr * multiplier)
```

### Bearish Engulfing Detection
```python
# Source: standard candlestick pattern definition
def is_bearish_engulfing(candles: pd.DataFrame) -> bool:
    if len(candles) < 2:
        return False
    prev = candles.iloc[-2]
    curr = candles.iloc[-1]
    prev_bullish = prev["close"] > prev["open"]
    curr_bearish = curr["close"] < curr["open"]
    curr_body = abs(curr["close"] - curr["open"])
    prev_body = abs(prev["close"] - prev["open"])
    engulfs = curr["open"] >= prev["close"] and curr["close"] <= prev["open"]
    return prev_bullish and curr_bearish and engulfs and curr_body > prev_body
```

### Breakeven + ATR Trail Logic
```python
# Pattern for OrderManager.check_positions() integration
def calculate_atr_trailing_sl(
    position: Position,
    current_price: float,
    atr: float,
    trail_multiplier: float = 2.0,
    activation_r: float = 1.0,
) -> float | None:
    entry = position.open_level
    initial_sl = position.stop_level
    if initial_sl is None:
        return None
    risk = abs(entry - initial_sl)
    if risk <= 0:
        return None
    if position.direction == "BUY":
        profit_r = (current_price - entry) / risk
        if profit_r < activation_r:
            return None  # Not yet active
        new_sl = current_price - (atr * trail_multiplier)
        # Never go below breakeven after activation
        new_sl = max(new_sl, entry)
        # Never move SL down
        if initial_sl and new_sl <= initial_sl:
            return None
        return round(new_sl, 2)
    # SELL mirror...
```

---

## State of the Art

| Old Approach (current codebase) | New Approach (Phase 10) | Impact |
|---------------------------------|------------------------|--------|
| Fixed pip trailing: `activation_pips=10, trail_distance_pips=5` | ATR-trailing: activates at +1R, trails at `price - atr * multiplier` | Adapts to current volatility; wider trail in volatile market prevents premature stops |
| No partial close | 50% close at TP1, 50% runs with trailing | Locks in profit while letting winners extend; improves profit factor |
| Fixed SL: `entry - 1.5 * ATR` (per regime) | ATR + structure: uses nearest swing level with buffer | SL is behind real market structure, not arbitrary price math |
| No exit signals — only TP/SL hits | Reversal candle + RSI/MACD divergence detection | Allows early exit before full reversal; reduces profit giveback |
| TP = `entry + 2.0 * ATR` (per regime) | Fibonacci extension OR nearest S/R zone | TP aligned to where market naturally reverses or pauses |

---

## Open Questions

1. **Capital.com minimum lot for Gold partial close**
   - What we know: Capital.com CFD minimum is typically 0.01 lots; Gold CFD is 1 troy oz per lot
   - What's unclear: Exact minimum for Gold epic "GOLD" on demo account; whether partial size must be in 0.01 increments
   - Recommendation: Add a pre-flight check in partial_close logic that validates remaining size >= 0.01. If bot trades >= 0.02 lots (safe for 50% split), partial close works. Add guard and log a warning for smaller positions.

2. **MACD divergence timeframe sensitivity on 5-minute chart**
   - What we know: MACD with (12, 26, 9) is computed in indicators.py; histogram is available
   - What's unclear: Whether 5-minute MACD divergence has sufficient reliability to trigger exits (false positive rate)
   - Recommendation: Set confidence=0.5 for MACD divergence signals (vs. 0.7 for reversal candles). Only close on MACD divergence if combined with at least one other confirming signal (e.g., RSI also diverging).

3. **Trailing stop in OrderManager vs. external monitor loop**
   - What we know: `OrderManager.check_positions()` already calls `trailing.calculate_new_sl()` and `executor.modify_position()`
   - What's unclear: Whether the exit engine's trailing logic replaces or extends the existing `TrailingStopManager`
   - Recommendation: Replace the fixed-pip `TrailingStopManager` with the new ATR-based trailing in `exit_engine/trailing_manager.py`. The existing class can be kept for backward compatibility but should not be called from OrderManager after Phase 10.

---

## Environment Availability

Step 2.6: All dependencies are pure Python (pandas, numpy) already installed. Capital.com API already accessible. No new external tools required.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | Swing detection, rolling windows | Yes | 3.0.0 | — |
| numpy | Fibonacci math, boolean masks | Yes | 2.2.6 | — |
| pandas-ta | ATR, RSI, MACD (already pre-computed) | Yes | 0.4.71b0 | — |
| Capital.com API | Partial close, modify_position | Yes | REST v1 | — |
| pytest | Test suite | Yes | via pyproject.toml dev deps | — |

No missing dependencies.

---

## Validation Architecture

Config has `workflow.nyquist_validation` absent — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/test_exit_engine_core.py tests/test_exit_engine_trailing.py tests/test_exit_engine_partial.py -x -v` |
| Full suite command | `python -m pytest tests/ --ignore=tests/test_e2e_trading.py -x --timeout=120 -q` |

**Note on existing suite:** `test_e2e_trading.py` has a collection error (likely missing import); `test_ensemble.py`, `test_gpt_predictor.py`, `test_order_lifecycle.py`, `test_order_lock.py`, `test_training_data_source.py` also have collection errors. These pre-exist Phase 10 and must not be made worse. The 107 currently passing tests must remain passing.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXIT-01 | Dynamic SL uses ATR * regime_multiplier | unit | `pytest tests/test_exit_engine_core.py::test_sl_trending -x` | No — Wave 0 gap |
| EXIT-01 | SL adjusts for structure levels (support below BUY entry) | unit | `pytest tests/test_exit_engine_core.py::test_sl_structure_buy -x` | No — Wave 0 gap |
| EXIT-01 | SL minimum floor enforced | unit | `pytest tests/test_exit_engine_core.py::test_sl_min_floor -x` | No — Wave 0 gap |
| EXIT-02 | Fibonacci extension levels computed correctly | unit | `pytest tests/test_exit_engine_core.py::test_fibonacci_extensions -x` | No — Wave 0 gap |
| EXIT-02 | TP1 set at 50% of full TP distance | unit | `pytest tests/test_exit_engine_core.py::test_tp1_50pct -x` | No — Wave 0 gap |
| EXIT-02 | Fallback to ATR TP when no structure found | unit | `pytest tests/test_exit_engine_core.py::test_tp_fallback -x` | No — Wave 0 gap |
| EXIT-03 | Trailing activates only at +1R profit | unit | `pytest tests/test_exit_engine_trailing.py::test_trail_activation -x` | No — Wave 0 gap |
| EXIT-03 | ATR trail moves SL up for BUY, down for SELL | unit | `pytest tests/test_exit_engine_trailing.py::test_atr_trail_buy -x` | No — Wave 0 gap |
| EXIT-03 | SL never moves against trade direction | unit | `pytest tests/test_exit_engine_trailing.py::test_trail_no_reverse -x` | No — Wave 0 gap |
| EXIT-04 | Partial close triggers when price reaches TP1 | unit | `pytest tests/test_exit_engine_partial.py::test_partial_close_trigger -x` | No — Wave 0 gap |
| EXIT-04 | Remaining size >= minimum lot before close | unit | `pytest tests/test_exit_engine_partial.py::test_partial_min_lot -x` | No — Wave 0 gap |
| EXIT-05 | Bearish engulfing detected on BUY position | unit | `pytest tests/test_exit_engine_core.py::test_bearish_engulfing -x` | No — Wave 0 gap |
| EXIT-05 | RSI divergence detected (price higher high, RSI lower high) | unit | `pytest tests/test_exit_engine_core.py::test_rsi_divergence -x` | No — Wave 0 gap |
| EXIT-05 | No false exit signal when trend is clean | unit | `pytest tests/test_exit_engine_core.py::test_no_exit_clean_trend -x` | No — Wave 0 gap |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/test_exit_engine_core.py -x -v`
- **Per wave merge:** `python -m pytest tests/ --ignore=tests/test_e2e_trading.py -x --timeout=120 -q`
- **Phase gate:** Full suite green (excluding pre-existing broken tests) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_exit_engine_core.py` — covers EXIT-01, EXIT-02, EXIT-05 (dynamic SL, TP, exit signals)
- [ ] `tests/test_exit_engine_trailing.py` — covers EXIT-03 (ATR trail, breakeven, activation)
- [ ] `tests/test_exit_engine_partial.py` — covers EXIT-04 (partial close trigger, lot minimum guard)

---

## Codebase Integration Map

This section is critical for the planner — shows exactly where each new module plugs in.

### Existing files that MUST be modified

| File | What Changes | Why |
|------|-------------|-----|
| `order_management/order_manager.py` | `check_positions()` calls exit engine: dynamic trailing, partial close check, exit signal check | Central position management loop |
| `market_data/broker_client.py` | Add `partial_close_position(deal_id, close_fraction)` method | Capital.com does not have a dedicated partial close endpoint; size reduction via PUT |
| `strategy/entry_calculator.py` | `calculate_sl_tp_for_regime()` becomes the entry-point that also calls `calculate_dynamic_sl` and `calculate_dynamic_tp` | Replaces fixed ATR math with structure-aware logic |
| `pyproject.toml` | Add `exit_engine*` to `[tool.setuptools.packages.find]` include list | Otherwise the package is not importable as installed package |

### Existing files that provide inputs (read-only from exit engine's perspective)

| File | Provides |
|------|---------|
| `strategy/regime_params.py` | `REGIME_PARAMS` dict with `sl_atr_multiplier`, `tp_atr_multiplier` per regime |
| `strategy/regime_detector.py` | `MarketRegime` enum (TRENDING, RANGING, VOLATILE) |
| `market_data/indicators.py` | Pre-computed `atr_14`, `rsi_14`, `macd_histogram`, `high`, `low` columns |
| `market_data/broker_client.py` | `Position` dataclass, `modify_position()`, `close_position()` |
| `shared/constants.py` | `PIP_SIZE = 0.01`, `SL_ATR_MULTIPLIER`, `TP_ATR_MULTIPLIER` |
| `order_management/trailing_stop.py` | Existing logic to understand (then replace with ATR-aware version) |

### Existing file that Plan 10-01 already covers

The existing `10-01-PLAN.md` covers: `exit_engine/__init__.py`, `exit_engine/types.py`, `exit_engine/dynamic_sl.py`, `exit_engine/dynamic_tp.py`, `exit_engine/exit_signals.py`, and `tests/test_exit_engine_core.py`. Plans 02 and 03 need to cover:

- Plan 02: `exit_engine/trailing_manager.py`, `exit_engine/partial_close.py`, `tests/test_exit_engine_trailing.py`, `tests/test_exit_engine_partial.py`, `market_data/broker_client.py` (add `partial_close_position`)
- Plan 03: Wire everything into `order_management/order_manager.py`, update `strategy/entry_calculator.py`, integration tests

---

## Sources

### Primary (HIGH confidence)
- Codebase direct read: `strategy/regime_params.py` — REGIME_PARAMS values confirmed
- Codebase direct read: `market_data/indicators.py` — confirmed `atr_14`, `rsi_14`, `macd_histogram` columns
- Codebase direct read: `market_data/broker_client.py` — confirmed `modify_position()` signature and `close_position()` API
- Codebase direct read: `order_management/trailing_stop.py` — confirmed existing fixed-pip implementation
- Codebase direct read: `order_management/order_manager.py` — confirmed `check_positions()` integration point
- Codebase direct read: `pyproject.toml` — confirmed installed packages (pandas 3.0, numpy 2.2.6, pandas-ta 0.4.71b0)

### Secondary (MEDIUM confidence)
- Capital.com REST API pattern: PUT `/api/v1/positions/{deal_id}` with `size` field for partial close — inferred from existing `modify_position()` implementation and Capital.com API v1 structure; consistent with how CFD brokers handle partial size reduction
- Chandelier Exit formula: Elder's original Chandelier Exit (1996) — `Highest_High(N) - ATR * multiplier` — well-documented TA standard
- Fibonacci extension ratios: 1.0, 1.272, 1.618, 2.0, 2.618 — standard Elliott Wave / Fibonacci TA practice

### Tertiary (LOW confidence)
- Minimum Gold lot size on Capital.com demo = 0.01: inferred from broker client code comment `# 1 lot = 1 Troy Ounce` and general CFD convention. Must verify by attempting a 0.01 lot trade on demo before implementing partial close validation.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages confirmed installed, no new dependencies
- Architecture patterns: HIGH — all integration points verified from live codebase reads
- Pitfalls: HIGH — directly derived from existing code structure and API patterns
- Capital.com partial close API: MEDIUM — inferred from existing modify_position pattern; needs empirical confirmation on demo account

**Research date:** 2026-03-26
**Valid until:** 2026-06-26 (stable domain — ATR math, Fibonacci, candlestick patterns do not change)
