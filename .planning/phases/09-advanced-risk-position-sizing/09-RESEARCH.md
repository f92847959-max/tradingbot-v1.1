# Phase 9: Advanced Risk & Position Sizing - Research

**Researched:** 2026-03-26
**Domain:** Quantitative risk management — Kelly Criterion, ATR-normalized sizing, portfolio heat, Monte Carlo simulation, equity curve filtering
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RISK-01 | Kelly Criterion berechnet optimale Positionsgroesse aus Win-Rate und RRR | Kelly formula verified; half/quarter modes needed for conservative trading |
| RISK-02 | Volatilitaets-basiertes Sizing normalisiert Positionen nach ATR | ATR-normalization pattern confirmed; baseline_atr=3.0 appropriate for XAUUSD 5min |
| RISK-03 | Portfolio Heat Management begrenzt offenes Gesamtrisiko auf max 5% | Simple sum-of-risk-amounts approach; no DB needed in hot path |
| RISK-04 | Monte Carlo Simulation zeigt Drawdown-Verteilung (1000+ Pfade) | numpy 2.2.6 confirmed; vectorized sim runs 1000x200 in 0.003s — far under 5s target |
| RISK-05 | Equity Curve Filter stoppt Trading bei Drawdown ueber Threshold | EMA-based filter; insufficient-data-safe (< ema_period points = always allow) |
</phase_requirements>

---

## Summary

Phase 9 adds five quantitative risk modules to replace the current static 1% fixed-fractional position sizing in `risk/position_sizing.py`. The existing `PositionSizer` class must be preserved without modification because `RiskManager.sizer` depends on it. All new modules are additive: `kelly_calculator.py`, `volatility_sizer.py`, `position_sizer.py` (new file, different name from existing), `monte_carlo.py`, `portfolio_heat.py`, and `equity_curve_filter.py`.

The Kelly Criterion formula (`f* = win_rate - (1 - win_rate) / RRR`) is well-established. In practice, full Kelly is aggressive; the standard industry approach for trading systems is Half-Kelly or Quarter-Kelly. For this bot, confidence tier drives Kelly mode: high ML confidence (>0.8) gets full Kelly fraction, medium (0.6-0.8) gets Half-Kelly, low (<0.6) gets Quarter-Kelly. The Kelly fraction is capped at 0.25 (25% of equity) as an absolute safety ceiling.

Monte Carlo simulation using NumPy's `np.random.default_rng()` is the correct modern approach. Benchmarking on the project machine shows 1000 paths x 200 trades completes in 0.003 seconds — well within the 5-second requirement. The equity curve filter uses a simple EMA with a 20-period lookback; when equity drops below its EMA, trading is restricted. Portfolio heat tracks raw risk-dollar amounts across open positions and enforces a 5% ceiling.

**Primary recommendation:** Implement all five modules as pure Python classes (no async, no DB) in the `risk/` package. Wire them into `RiskManager` additively via new optional constructor parameters that default to preserving backward compatibility. The `AdvancedPositionSizer` facade is the Phase 10 interface contract — its module-level `get_position_size()` function must be stable.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.2.6 (verified in venv) | Vectorized Monte Carlo paths, percentile calculations, EMA | Already a project dependency; `np.random.default_rng` is the modern numpy API |
| Python stdlib (math, dataclasses, logging) | 3.12.x | Kelly math, dataclasses for SimulationResult, structured logging | No external dependencies needed for pure math modules |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest 9.0.2 | 9.0.2 (system Python) | TDD unit tests for all modules | All new modules use TDD (tests written first) |
| pytest-asyncio | NOT INSTALLED | Async test support | Required for RiskManager integration tests; must be installed before async tests run |

**Installation (missing dependency):**
```bash
cd "C:/Users/fuhhe/OneDrive/Desktop/ai/ai/ai trading gold"
pip install pytest-asyncio>=0.24.0
```

**Version verification (already confirmed):**
```bash
python -c "import numpy; print(numpy.__version__)"  # 2.2.6
python -m pytest --version                           # 9.0.2
```

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| numpy vectorized MC | scipy.stats Monte Carlo | scipy adds import weight; numpy already installed and sufficient |
| Custom EMA in equity_curve_filter.py | pandas-ta EMA | pandas-ta is a project dep but overkill for a single in-memory EMA; pure Python is simpler and has no DF dependency |
| Python dataclass for SimulationResult | Pydantic BaseModel | Pydantic adds serialization features but is overkill for an in-memory result; stdlib dataclass is sufficient |

---

## Architecture Patterns

### Recommended Project Structure (new files only)
```
risk/
├── __init__.py              # extend: export all new classes
├── kelly_calculator.py      # NEW: KellyCalculator class (pure math)
├── volatility_sizer.py      # NEW: VolatilitySizer class (pure math)
├── position_sizer.py        # NEW: AdvancedPositionSizer + module-level functions
├── monte_carlo.py           # NEW: MonteCarloSimulator + SimulationResult
├── portfolio_heat.py        # NEW: PortfolioHeatManager
├── equity_curve_filter.py   # NEW: EquityCurveFilter
├── position_sizing.py       # UNCHANGED (PositionSizer for backward compat)
├── risk_manager.py          # MODIFIED: add advanced sizer + 2 new checks + 5 new methods
├── kill_switch.py           # UNCHANGED
└── pre_trade_check.py       # UNCHANGED

tests/
├── test_kelly_calculator.py      # NEW: >= 8 tests
├── test_volatility_sizer.py      # NEW: >= 6 tests
├── test_position_sizer_advanced.py # NEW: >= 9 tests
├── test_monte_carlo.py            # NEW: >= 12 tests
├── test_portfolio_heat.py         # NEW: >= 10 tests
├── test_equity_curve_filter.py    # NEW: >= 9 tests
└── test_risk_integration_advanced.py # NEW: >= 9 tests
```

### Pattern 1: Pure Math Module (Kelly, Volatility, Portfolio Heat, Equity Curve)
**What:** Stateless or simple-stateful classes with no async, no DB, no external imports.
**When to use:** Any calculation that can be done entirely in memory.
**Example:**
```python
# risk/kelly_calculator.py
import logging
logger = logging.getLogger(__name__)

class KellyCalculator:
    def kelly_fraction(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)"""
        if avg_loss <= 0 or avg_win <= 0 or win_rate <= 0:
            return 0.0
        rrr = avg_win / avg_loss
        f = win_rate - (1.0 - win_rate) / rrr
        clamped = max(0.0, min(f, 0.25))  # never risk > 25%
        logger.debug("Kelly: win_rate=%.3f, RRR=%.2f -> f*=%.4f (clamped=%.4f)", win_rate, rrr, f, clamped)
        return clamped

    def half_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        return self.kelly_fraction(win_rate, avg_win, avg_loss) * 0.5

    def quarter_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        return self.kelly_fraction(win_rate, avg_win, avg_loss) * 0.25

    def compute_from_trades(self, trades: list[dict]) -> float:
        """Requires >= 30 trades. Returns half_kelly by default."""
        if len(trades) < 30:
            logger.warning("Insufficient trades (%d < 30) for Kelly estimation", len(trades))
            return 0.0
        wins = [t for t in trades if t.get("net_pnl", 0) > 0]
        losses = [t for t in trades if t.get("net_pnl", 0) < 0]
        if not wins or not losses:
            return 0.0
        win_rate = len(wins) / len(trades)
        avg_win = sum(abs(t["net_pnl"]) for t in wins) / len(wins)
        avg_loss = sum(abs(t["net_pnl"]) for t in losses) / len(losses)
        return self.half_kelly(win_rate, avg_win, avg_loss)
```

### Pattern 2: Vectorized Monte Carlo with numpy
**What:** Use numpy matrix operations to run all paths simultaneously, avoiding Python loops over paths.
**When to use:** Any simulation with >= 100 paths.
**Example:**
```python
# risk/monte_carlo.py
import numpy as np
from dataclasses import dataclass

@dataclass
class SimulationResult:
    max_drawdown_pcts: list[float]
    final_equities: list[float]
    ruin_probability: float
    drawdown_percentiles: dict   # keys: p50, p75, p90, p95, p99
    return_percentiles: dict     # keys: p5, p25, p50, p75, p95
    num_paths: int
    num_trades: int

class MonteCarloSimulator:
    def __init__(self, ruin_threshold: float = 0.5) -> None:
        self.ruin_threshold = ruin_threshold

    def simulate(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int = 200,
        num_paths: int = 1000,
        initial_equity: float = 10000.0,
        position_fraction: float = 0.02,
        seed: int | None = None,
    ) -> SimulationResult:
        rng = np.random.default_rng(seed)
        # Shape: (num_paths, num_trades) — True where trade is a win
        outcomes = rng.random((num_paths, num_trades)) < win_rate

        equities = np.full(num_paths, initial_equity, dtype=float)
        peaks = equities.copy()
        max_dds = np.zeros(num_paths)

        for t in range(num_trades):
            wins = outcomes[:, t]
            gain = equities * position_fraction * (avg_win / avg_loss)
            loss = equities * position_fraction
            equities = np.where(wins, equities + gain, equities - loss)
            peaks = np.maximum(peaks, equities)
            dd = (peaks - equities) / peaks * 100.0
            max_dds = np.maximum(max_dds, dd)

        returns = (equities - initial_equity) / initial_equity * 100.0
        ruin = float(np.mean(max_dds >= self.ruin_threshold * 100.0))

        return SimulationResult(
            max_drawdown_pcts=max_dds.tolist(),
            final_equities=equities.tolist(),
            ruin_probability=ruin,
            drawdown_percentiles={
                "p50": float(np.percentile(max_dds, 50)),
                "p75": float(np.percentile(max_dds, 75)),
                "p90": float(np.percentile(max_dds, 90)),
                "p95": float(np.percentile(max_dds, 95)),
                "p99": float(np.percentile(max_dds, 99)),
            },
            return_percentiles={
                "p5": float(np.percentile(returns, 5)),
                "p25": float(np.percentile(returns, 25)),
                "p50": float(np.percentile(returns, 50)),
                "p75": float(np.percentile(returns, 75)),
                "p95": float(np.percentile(returns, 95)),
            },
            num_paths=num_paths,
            num_trades=num_trades,
        )
```

### Pattern 3: Additive Extension of RiskManager (preserve backward compat)
**What:** Add new optional constructor parameters with safe defaults; add new checks without changing existing check numbering.
**When to use:** Any time an existing class used by many callers must be extended.
**Example:**
```python
# risk/risk_manager.py extension (sketch)
class RiskManager:
    def __init__(
        self,
        # ALL existing params unchanged ...
        kelly_mode: str = "half",           # NEW optional
        atr_baseline: float = 3.0,          # NEW optional
        max_portfolio_heat_pct: float = 5.0, # NEW optional
        equity_curve_ema_period: int = 20,   # NEW optional
        equity_curve_filter_enabled: bool = True,  # NEW optional
    ) -> None:
        # existing init code unchanged ...
        # NEW additions at bottom of __init__:
        self.advanced_sizer = AdvancedPositionSizer(...)
        self.portfolio_heat = PortfolioHeatManager(max_heat_pct=max_portfolio_heat_pct)
        self.equity_filter = EquityCurveFilter(ema_period=equity_curve_ema_period, enabled=equity_curve_filter_enabled)

    async def approve_trade(
        self,
        # ALL existing params unchanged ...
        confidence: float = 0.7,  # NEW with safe default
        atr: float = 3.0,         # NEW with safe default
    ) -> RiskApproval:
        # ... existing 11 checks ...
        # NEW check 12: portfolio heat
        # NEW check 13: equity curve filter
        # lot_size: use advanced_sizer if Kelly data available, else fall back to self.sizer
```

### Pattern 4: ATR-Normalized Sizing
**What:** The position size inverse-scales with ATR relative to a baseline. High ATR = smaller position.
**Formula:** `factor = baseline_atr / max(current_atr, 0.01)`, clamped to `[min_scale, max_scale]`.
**XAUUSD 5min baseline:** ATR-14 ≈ 3.0 price points is the empirically reasonable baseline for normal volatility.
**Clamping:** `min_scale=0.25` (never go below 25% of base size), `max_scale=1.5` (never exceed 150%).

### Anti-Patterns to Avoid
- **Modifying `risk/position_sizing.py`:** The existing `PositionSizer` is used directly by `RiskManager.sizer`. Changing it breaks backward compatibility. Create `risk/position_sizer.py` (different filename) for the new class.
- **Using full Kelly without capping:** Full Kelly maximizes long-run geometric growth but can produce position fractions > 50% with a strong edge. Always cap at 0.25 (25%) maximum.
- **Negative Kelly fraction:** When `win_rate - (1 - win_rate)/RRR < 0`, the system has no edge. Return 0.0 (don't trade), not a negative number.
- **Computing Kelly from < 30 trades:** Small samples produce unreliable win rates. Require minimum 30 trades; return 0.0 and fall back to `base_risk_pct` if fewer.
- **Python for-loop over paths in Monte Carlo:** Use numpy vectorization. Looping 1000 paths in Python would take seconds; vectorized numpy takes milliseconds.
- **Async in pure math modules:** `kelly_calculator.py`, `volatility_sizer.py`, `monte_carlo.py`, `portfolio_heat.py`, `equity_curve_filter.py` must NOT import asyncio or DB modules. Pure Python only.
- **EMA seeding wrong:** When initializing the EMA, seed with SMA of the first `ema_period` data points, not the first data point alone. The plans' EMA code handles this correctly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vectorized random draws | Manual Python loops over paths | `np.random.default_rng().random((num_paths, num_trades))` | 100x faster; proper seeding for reproducibility |
| Percentile calculation | Custom sort+index | `np.percentile(array, [50, 75, 90, 95, 99])` | Handles edge cases, optimized |
| EMA computation (single series) | Custom recursive loop | The EMA formula is simple enough to inline: `ema = price * k + ema * (1 - k)` | pandas-ta EMA requires a DataFrame; for a list of equity values, inline is simpler |
| Settings parsing | Custom env reader | `pydantic-settings BaseSettings` (already in use) | Already in `config/settings.py`; just add new fields |

**Key insight:** All the heavy numerical work is done by numpy. Kelly and portfolio heat are elementary arithmetic — no library needed. The only dependency to be aware of is pytest-asyncio for integration tests.

---

## Common Pitfalls

### Pitfall 1: pytest-asyncio Not Installed — Async Tests Silently Skip or Fail
**What goes wrong:** Tests decorated with `@pytest.mark.asyncio` show as `Failed: async def` or emit `PytestUnknownMarkWarning`. This is already happening for 5 existing tests in `test_risk.py` and `test_risk_manager.py`.
**Why it happens:** The system Python environment does not have `pytest-asyncio` installed (confirmed: `ModuleNotFoundError: No module named 'pytest_asyncio'`). `pyproject.toml` specifies `pytest-asyncio>=0.24.0` in `[project.optional-dependencies] dev` but it was not installed.
**How to avoid:** Install before running any integration tests: `pip install pytest-asyncio>=0.24.0`. The `pyproject.toml` has `asyncio_mode = "auto"` in `[tool.pytest.ini_options]` — once pytest-asyncio is installed, all async tests run automatically without `@pytest.mark.asyncio` decorators.
**Warning signs:** `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio` in test output.

### Pitfall 2: Breaking Existing `PositionSizer` via File Name Collision
**What goes wrong:** Creating `risk/position_sizer.py` (the new advanced sizer) must NOT overwrite `risk/position_sizing.py` (the existing one). The filenames differ by one character.
**Why it happens:** The plan explicitly calls the new file `position_sizer.py` (no 'ing') to avoid this. Any automated tool that confuses the names would break `RiskManager`.
**How to avoid:** Verify after creation: `risk/position_sizing.py` (existing, unchanged) and `risk/position_sizer.py` (new) must both exist. Run `python -m pytest tests/test_risk.py tests/test_risk_manager.py` after the new file is created to confirm zero regressions.

### Pitfall 3: Kelly Fraction with No Trade History Falls Back Incorrectly
**What goes wrong:** When the bot starts fresh (zero trade history), `compute_from_trades([])` returns 0.0. If the `AdvancedPositionSizer` interprets `_kelly_fraction = 0.0` as "risk zero", no trades execute.
**Why it happens:** The fallback logic must distinguish "no Kelly data yet" from "zero Kelly = no edge". The plan handles this: when `_kelly_fraction == 0.0`, fall back to `base_risk_pct` (the config value), not to zero position size.
**How to avoid:** In `get_position_size()`, check `if self._kelly_fraction == 0.0: use base_risk_pct as risk percentage`. Test explicitly: fresh `AdvancedPositionSizer` with no `set_trade_stats()` call must return a valid lot size.

### Pitfall 4: Portfolio Heat Tracks Risk Amount Not Lot Size
**What goes wrong:** Heat is tracked as `risk_amount = abs(entry_price - stop_loss) * lot_size`, not just lot size. Without this formula, heat calculations are meaningless.
**Why it happens:** Portfolio heat must measure actual money at risk, which depends on SL distance times lot size. The trading loop wiring in Plan 09-03 computes this correctly: `risk_amount = abs(entry_price - stop_loss) * approval.lot_size`.
**How to avoid:** Verify the `on_position_opened` call in the trading loop uses the formula above, not just `approval.lot_size`.

### Pitfall 5: EMA Not Warmed Up (Insufficient Data Defaults)
**What goes wrong:** On system restart or with a new account, fewer than `ema_period` (20) equity data points exist. The filter must not block trading during warmup.
**Why it happens:** EMA requires `ema_period` data points before it's meaningful. Blocking trading while warming up would prevent the bot from functioning after a restart.
**How to avoid:** `EquityCurveFilter.is_trading_allowed()` returns `True` when `len(self._equity_history) < self.ema_period`. This is the "insufficient data" safe default.

### Pitfall 6: Monte Carlo RNG Seeding Affects Test Reproducibility
**What goes wrong:** Without a fixed seed, Monte Carlo tests may produce different ruin probability values across runs, making the numerical assertions flaky.
**Why it happens:** `np.random.default_rng()` without seed produces random state per call.
**How to avoid:** Pass `seed=42` in tests. In production, omit seed (None) for genuine randomness. Test assertions on ruin probability use direction checks (`< 0.1` for strong edge) rather than exact equality.

### Pitfall 7: `risk/__init__.py` Currently Empty
**What goes wrong:** The existing `risk/__init__.py` is an empty file (0 bytes confirmed). Plan 09-03 adds exports to it. If the file is accidentally re-created as empty, all `from risk import ...` imports in tests will break.
**Why it happens:** The plan extends (not replaces) the init file.
**How to avoid:** Read the existing file before writing. Since it's empty, write a fresh `__init__.py` with all exports. No content is lost.

---

## Code Examples

Verified patterns from the existing codebase and the plan specifications:

### Kelly Criterion Math (verified manually)
```python
# kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
# RRR = 2.0 / 1.0 = 2.0
# f* = 0.6 - (1 - 0.6) / 2.0 = 0.6 - 0.4/2 = 0.6 - 0.2 = 0.4
# clamped to 0.25 (max cap)
# half_kelly = 0.25 * 0.5 = 0.125  <- plan says 0.15 but 0.4 clamped to 0.25 * 0.5 = 0.125
# NOTE: Plan test says half_kelly(0.6, 2.0, 1.0) == 0.15 meaning they DON'T clamp before halving
# The clamping must happen AFTER the half/quarter multiplication, or the Kelly fraction
# must be clamped to 0.30 (not 0.25) so half=0.15 works.
# RESOLUTION: Plan test: kelly_fraction(0.6, 2.0, 1.0) == 0.3 (unclamped result IS 0.4, not 0.3)
# Actual formula gives 0.4. Plan says 0.3. RE-CHECK:
# f* = 0.6 - 0.4/2.0 = 0.6 - 0.2 = 0.4  [correct math]
# BUT plan says result is 0.3. This suggests the plan may have a different formula.
# POSSIBLE: plan uses f* = W - (1-W)/R where R is RRR directly
# With R=2: f* = 0.6 - 0.4/2 = 0.4 -- does NOT equal 0.3.
# ALTERNATIVE FORMULA often seen: f* = (bp - q) / b where b=odds, p=win_rate, q=1-p
# With b=avg_win/avg_loss: f* = (2*0.6 - 0.4) / 2 = (1.2-0.4)/2 = 0.8/2 = 0.4 -- still 0.4
# CONCLUSION: The plan's test assertion kelly_fraction(0.6, 2.0, 1.0) == 0.3 may contain
# an error, OR the plan uses a different parameterization (avg_win=2.0 means 2x the avg_loss
# as the gain amount, making RRR=2/1=2 but Kelly sometimes uses net odds).
# THE IMPLEMENTER must verify: does the test pass when f*=0.4 or when f*=0.3?
# The safest approach: implement the standard formula (result=0.4) and adjust the plan's
# test assertion if needed. Document the discrepancy.
```

**IMPORTANT NOTE FOR PLANNER:** The plan's test asserts `kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0) == 0.3`. The standard Kelly formula gives 0.4 for these inputs. This discrepancy must be resolved before implementation. Two possibilities:
1. The plan uses a formula that normalizes differently (e.g., `f* = win_rate - (1-win_rate) * avg_loss / avg_win`, which gives `0.6 - 0.4*0.5 = 0.6 - 0.2 = 0.4`).
2. The plan intends `avg_win=2.0` to mean "win 2 units" with `avg_loss=1.0` meaning "lose 1 unit", giving RRR=2, Kelly=0.4.
3. Or the test has a typo and should be 0.4, not 0.3.

**Recommendation:** Implement `f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)`, verify the numeric output, and align the test to match the implementation. The mathematical correctness of the formula matters more than matching a potentially-wrong assertion.

### ATR Factor Calculation (verified against plan spec)
```python
# volatility_sizer.py — calculate_atr_factor
# baseline_atr=3.0, atr=6.0 -> factor = 3.0/6.0 = 0.5 -> clamp(0.5, 0.25, 1.5) = 0.5  OK
# baseline_atr=3.0, atr=1.5 -> factor = 3.0/1.5 = 2.0 -> clamp(2.0, 0.25, 1.5) = 1.5  OK
# baseline_atr=3.0, atr=0.0 -> factor = 3.0/max(0.0,0.01) = 3.0/0.01 = 300 -> clamp = 1.5  OK

def calculate_atr_factor(self, atr: float) -> float:
    factor = self.baseline_atr / max(atr, 0.01)
    return max(self.min_scale, min(factor, self.max_scale))
```

### EMA Seeding for Equity Curve Filter
```python
# equity_curve_filter.py — update()
# EMA seed: use SMA of first ema_period points, then standard EMA update
k = 2.0 / (self.ema_period + 1)
if self._ema == 0.0 and len(self._equity_history) >= self.ema_period:
    # First time enough data is available: seed with SMA
    self._ema = sum(self._equity_history[-self.ema_period:]) / self.ema_period
elif self._ema != 0.0:
    # Normal update
    self._ema = equity * k + self._ema * (1 - k)
```

### `approve_trade` Backward-Compatible Signature Extension
```python
# risk/risk_manager.py — extended approve_trade
async def approve_trade(
    self,
    direction: str,
    entry_price: float,
    stop_loss: float,
    current_equity: float,
    available_margin: float,
    open_positions: int,
    trades_today: int,
    consecutive_losses: int,
    current_spread: float,
    has_open_same_direction: bool,
    weekly_loss_pct: float = 0.0,
    confidence: float = 0.7,   # NEW: default preserves old call sites
    atr: float = 3.0,          # NEW: default preserves old call sites
) -> RiskApproval:
```

### Trading Loop Wiring (from Plan 09-03, referencing trading_loop.py line 170)
```python
# In _trading_tick(), replace the existing approve_trade call block:
current_atr = float(df.iloc[-1].get("atr_14", 3.0)) if "atr_14" in df.columns else 3.0

approval = await self.risk.approve_trade(
    direction=direction,
    entry_price=entry_price,
    stop_loss=stop_loss,
    current_equity=account.balance,
    available_margin=account.available,
    open_positions=open_positions,
    trades_today=trades_today,
    consecutive_losses=consecutive_losses,
    current_spread=current_spread,
    has_open_same_direction=self.orders.has_position_in_direction(direction),
    weekly_loss_pct=weekly_loss_pct,
    confidence=confidence,       # ADD
    atr=current_atr,             # ADD
)

# After trade opened:
if trade:
    risk_amount = abs(entry_price - stop_loss) * approval.lot_size
    self.risk.on_position_opened(risk_amount, account.balance)
```

---

## Runtime State Inventory

This phase involves no rename/rebrand/migration. All changes are additive code. No runtime state inventory needed.

**Nothing found in any category** — Phase 9 adds new modules and extends existing classes. No stored data, live service configs, OS-registered state, secrets, or build artifacts are affected.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `np.random.RandomState` (legacy) | `np.random.default_rng()` (Generator API) | NumPy 1.17+ | Better statistical properties, reproducibility, faster |
| Full Kelly in production | Fractional Kelly (half or quarter) | Industry standard since 1990s | Reduces variance dramatically; most practitioners use Half-Kelly |
| Fixed fractional sizing (1% always) | Dynamic sizing (Kelly + ATR adjustment) | Project Phase 9 | Adapts to edge strength and market volatility |

**Deprecated/outdated:**
- `np.random.seed()` + `np.random.rand()`: Replaced by `np.random.default_rng(seed)` + `rng.random()`. Old API is thread-unsafe and has worse statistical properties.

---

## Open Questions

1. **Kelly Test Assertion Discrepancy**
   - What we know: Standard Kelly formula gives `f*(0.6, 2.0, 1.0) = 0.4`, but the plan asserts `== 0.3`.
   - What's unclear: Whether the plan uses a non-standard parameterization, has a typo, or expects pre-clamped half-Kelly to be 0.15 (which would require unclamped f*=0.30).
   - Recommendation: When implementing Task 1 of Plan 09-01, verify numerically and align the test to the implementation. If `f*=0.30` is desired, the formula being used is likely `f* = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win` which gives `(0.6*2 - 0.4*1) / 2 = (1.2-0.4)/2 = 0.4` — still 0.4. The only formula giving 0.3 for these inputs would be something unusual. **The implementer should write the mathematically correct formula and adjust the test number.**

2. **`atr_14` Column Availability in df**
   - What we know: The trading loop reads `df.iloc[-1].get("atr_14", 3.0)` for the ATR. The feature engineering pipeline must add an `atr_14` column to the candles DataFrame.
   - What's unclear: Whether `atr_14` is consistently present in the df passed to `_trading_tick`.
   - Recommendation: The fallback `3.0` in the `.get("atr_14", 3.0)` call handles absence gracefully. Verify by checking `market_data/indicators.py` for the column name.

3. **Position Close Heat Tracking**
   - What we know: `on_position_closed` must be called in the trading loop when a trade closes. The current loop monitors positions in `_monitor_open_positions` but this method is in the TradingSystem class, not in the mixin shown.
   - What's unclear: Exactly where in the codebase position closes are detected and how to hook `on_position_closed` there.
   - Recommendation: Plan 09-03 Task 2 must also read `trading/monitors.py` to find the close event hook point.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | All modules | Yes | 3.12.x | — |
| numpy | MonteCarloSimulator, VolatilitySizer (numpy percentile) | Yes | 2.2.6 | — |
| pytest | All tests | Yes | 9.0.2 | — |
| pytest-asyncio | RiskManager integration tests, test_risk.py async tests | No | — | Install: `pip install pytest-asyncio>=0.24.0` |
| pandas-ta | Feature engineering (atr_14 column) | Yes (in pyproject.toml deps) | — | 3.0 hardcoded default |

**Missing dependencies with no fallback:**
- None that block the pure-math modules.

**Missing dependencies with fallback:**
- `pytest-asyncio`: 5 existing async tests in test_risk.py and test_risk_manager.py already fail without it. The new integration tests (test_risk_integration_advanced.py) will also need it. **Install before running any integration tests.**

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `python -m pytest tests/test_kelly_calculator.py tests/test_volatility_sizer.py tests/test_monte_carlo.py tests/test_portfolio_heat.py tests/test_equity_curve_filter.py -v --tb=short` |
| Full suite command | `python -m pytest tests/test_kelly_calculator.py tests/test_volatility_sizer.py tests/test_position_sizer_advanced.py tests/test_monte_carlo.py tests/test_portfolio_heat.py tests/test_equity_curve_filter.py tests/test_risk_integration_advanced.py tests/test_risk.py tests/test_risk_manager.py -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RISK-01 | Kelly fraction correct for win_rate=0.6, RRR=2.0 | unit | `python -m pytest tests/test_kelly_calculator.py -v` | Wave 0 |
| RISK-01 | half_kelly and quarter_kelly modes | unit | `python -m pytest tests/test_kelly_calculator.py -v` | Wave 0 |
| RISK-01 | compute_from_trades requires >= 30 trades | unit | `python -m pytest tests/test_kelly_calculator.py -v` | Wave 0 |
| RISK-02 | ATR factor = 0.5 when atr=6, baseline=3 | unit | `python -m pytest tests/test_volatility_sizer.py -v` | Wave 0 |
| RISK-02 | ATR factor clamped to min/max | unit | `python -m pytest tests/test_volatility_sizer.py -v` | Wave 0 |
| RISK-02 | AdvancedPositionSizer returns smaller lot at higher ATR | unit | `python -m pytest tests/test_position_sizer_advanced.py -v` | Wave 0 |
| RISK-03 | Portfolio heat blocked at >= 5% | unit | `python -m pytest tests/test_portfolio_heat.py -v` | Wave 0 |
| RISK-03 | approve_trade check 12 blocks when heat at max | integration | `python -m pytest tests/test_risk_integration_advanced.py -v` | Wave 0 |
| RISK-04 | MC sim 1000 paths produces drawdown_percentiles keys | unit | `python -m pytest tests/test_monte_carlo.py -v` | Wave 0 |
| RISK-04 | ruin_probability < 0.1 for strong edge | unit | `python -m pytest tests/test_monte_carlo.py -v` | Wave 0 |
| RISK-04 | seed=42 reproducible | unit | `python -m pytest tests/test_monte_carlo.py -v` | Wave 0 |
| RISK-05 | Equity curve filter allows trading above EMA | unit | `python -m pytest tests/test_equity_curve_filter.py -v` | Wave 0 |
| RISK-05 | Equity curve filter blocks trading below EMA | unit | `python -m pytest tests/test_equity_curve_filter.py -v` | Wave 0 |
| RISK-05 | approve_trade check 13 blocks when equity below EMA | integration | `python -m pytest tests/test_risk_integration_advanced.py -v` | Wave 0 |

### Sampling Rate
- **Per task commit (Wave 1, pure-math modules):** `python -m pytest tests/test_kelly_calculator.py tests/test_volatility_sizer.py tests/test_monte_carlo.py tests/test_portfolio_heat.py tests/test_equity_curve_filter.py -v --tb=short`
- **Per task commit (Wave 2, integration):** Full suite command above
- **Phase gate:** Full suite green before phase 9 is marked complete

### Wave 0 Gaps
- [ ] `tests/test_kelly_calculator.py` — covers RISK-01 (>= 8 tests)
- [ ] `tests/test_volatility_sizer.py` — covers RISK-02 (>= 6 tests)
- [ ] `tests/test_position_sizer_advanced.py` — covers RISK-01 + RISK-02 combined (>= 9 tests)
- [ ] `tests/test_monte_carlo.py` — covers RISK-04 (>= 12 tests)
- [ ] `tests/test_portfolio_heat.py` — covers RISK-03 (>= 10 tests)
- [ ] `tests/test_equity_curve_filter.py` — covers RISK-05 (>= 9 tests)
- [ ] `tests/test_risk_integration_advanced.py` — covers RISK-03 + RISK-05 wired into RiskManager (>= 9 tests)
- [ ] pytest-asyncio install: `pip install pytest-asyncio>=0.24.0` (needed for integration tests)

---

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `risk/position_sizing.py`, `risk/risk_manager.py`, `risk/pre_trade_check.py`, `risk/kill_switch.py` — read in full
- Direct codebase analysis: `config/settings.py`, `trading/trading_loop.py` — read in full
- Plan files: `09-01-PLAN.md`, `09-02-PLAN.md`, `09-03-PLAN.md` — read in full; all implementation details are already specified
- Benchmark verification: Monte Carlo numpy vectorized performance confirmed (0.003s for 1000x200 on project machine)

### Secondary (MEDIUM confidence)
- Kelly Criterion formula: Established quantitative finance formula, verified manually against multiple standard references. The standard formula `f* = p - q/b` (where p=win_rate, q=1-p, b=reward/risk) is equivalent to `f* = win_rate - (1-win_rate)/RRR`.
- Half-Kelly as industry standard: Well-established in quantitative trading literature (Ed Thorp, Ralph Vince). Verified against the plan's design choice.

### Tertiary (LOW confidence)
- XAUUSD ATR-14 baseline of 3.0 for 5-minute candles: Stated in plan with no backtesting verification. This is a reasonable heuristic that the `atr_guard` in existing `position_sizing.py` uses a threshold of 5.0, suggesting 3.0 as normal is plausible.

---

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` was found in the project root. Conventions observed from the existing codebase:

| Constraint | Source | Directive |
|------------|--------|-----------|
| English code comments | Existing code style | All code comments in English; user-facing strings may be German |
| Python 3.11+ type hints | pyproject.toml `requires-python = ">=3.11"` | Use `float \| None` syntax, not `Optional[float]` |
| Logging, not print | All existing modules | Use `logger = logging.getLogger(__name__)` |
| Pure math modules: no async, no DB | Plan specifications | kelly_calculator, volatility_sizer, monte_carlo, portfolio_heat, equity_curve_filter must import ONLY stdlib + numpy |
| ruff linter | pyproject.toml `[tool.ruff]` | Line length 100, target Python 3.11 |
| TDD: tests first | All plans specify `tdd="true"` | Write failing tests before implementing; verify RED then GREEN |
| Backward compatibility: PositionSizer unchanged | risk_manager.py depends on it | `risk/position_sizing.py` must not be modified |
| `asyncio_mode = "auto"` in pytest config | pyproject.toml | No `@pytest.mark.asyncio` needed once pytest-asyncio is installed |

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — numpy already installed and benchmarked; all other deps verified
- Architecture: HIGH — all three plans are fully detailed; implementation is reading the plan, not designing
- Pitfalls: HIGH — most pitfalls discovered by direct analysis of failing tests and code (pytest-asyncio missing, filename collision risk, Kelly discrepancy)
- Kelly math discrepancy: MEDIUM — the test assertion issue is real but resolvable at implementation time

**Research date:** 2026-03-26
**Valid until:** 2026-06-26 (stable financial math domain; numpy API is stable)
