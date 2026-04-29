# Phase 5: Backtesting & Validation - Research

**Researched:** 2026-03-08
**Domain:** Backtesting framework enhancement, walk-forward out-of-sample validation, performance reporting
**Confidence:** HIGH

## Summary

Phase 5 requires enhancing an **already substantial** backtesting and walk-forward validation infrastructure to meet four specific requirements: out-of-sample validation (BACK-01), realistic cost modeling (BACK-02), comprehensive performance reporting (BACK-03), and cross-period consistency validation (BACK-04).

The critical insight from code review is that much of the machinery already exists. The `Backtester` class already handles spread and slippage, the `WalkForwardValidator` already runs expanding-window validation, and both `Backtester._generate_report()` and `ModelEvaluator.evaluate_trading()` already compute Sharpe, max drawdown, win rate, and profit factor. The `AdvancedBacktester` (in `strategy/backtesting/advanced_backtester.py`) adds dynamic cost simulation but is not integrated into the training pipeline. What is missing is: (1) commission support in the backtester, (2) a dedicated backtest runner that uses trained models on out-of-sample data (currently backtesting is embedded in training evaluation), (3) a consolidated performance report with per-window breakdown suitable for Phase 5 UAT, and (4) enforcement of the UAT consistency criteria (>60% positive windows, no window >20% drawdown).

**Primary recommendation:** Build a standalone backtest orchestrator (`scripts/run_backtest.py`) that loads a trained model version, runs walk-forward backtesting on out-of-sample test data with full cost modeling (spread + slippage + commission), generates a JSON + console report meeting BACK-03, and enforces BACK-04 consistency checks. Enhance the existing `Backtester` to support commissions (BACK-02). Reuse existing walk-forward window infrastructure rather than rebuilding it.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BACK-01 | Backtesting framework validates strategy on out-of-sample data | Existing `WalkForwardValidator` already splits OOS test windows; need a standalone backtest runner that loads trained models and evaluates on held-out test periods |
| BACK-02 | Backtest includes realistic costs (spread, slippage, commissions) | `Backtester` already deducts spread + slippage; add `commission_per_trade` parameter (Capital.com CFDs charge via spread, so commission can default to 0 but must be configurable) |
| BACK-03 | Backtest report shows key metrics (Sharpe ratio, max drawdown, win rate, profit factor) | `Backtester._generate_report()` already computes all four metrics; need a consolidated report format that includes per-window + aggregate views |
| BACK-04 | Walk-forward backtest shows consistent performance across time periods | Need per-window metric extraction + consistency checks (>60% positive windows, no window >20% drawdown) -- this is the primary new logic |
</phase_requirements>

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | existing | Array operations, equity curves | Already used throughout backtester |
| pandas | existing | DataFrames, time series | Already used for data handling |
| xgboost | existing | Model inference | Already trained models |
| lightgbm | existing | Model inference | Already trained models |

### Supporting (already in project)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib | existing | Equity curve charts, drawdown visualization | Report generation |
| json | stdlib | Report serialization | Saving backtest reports |

### No New Dependencies Needed
This phase requires zero new library installations. All required functionality is built on numpy, pandas, and the existing model/backtester infrastructure.

## Architecture Patterns

### Current Codebase Structure (relevant files)
```
ai_engine/
  training/
    backtester.py          # Backtester class (spread/slippage, run/run_simple)
    walk_forward.py        # WalkForwardValidator, generate_training_report
    evaluation.py          # ModelEvaluator.evaluate_trading (Sharpe, DD, WR, PF)
    pipeline.py            # TrainingPipeline (trains + evaluates)
    trainer.py             # ModelTrainer (owns sub-components)
    model_versioning.py    # Version dirs, production.json pointer
    trade_filter.py        # probs_to_trade_signals, tune_trade_filter
strategy/
  backtesting/
    advanced_backtester.py # AdvancedBacktester (dynamic costs, unused in pipeline)
  regime_detector.py       # RegimeDetector + MarketRegime enum
  regime_params.py         # REGIME_PARAMS per-regime TP/SL multipliers
scripts/
  train_models.py          # CLI for training
```

### Recommended New/Modified Structure
```
ai_engine/
  training/
    backtester.py          # MODIFY: add commission_per_trade parameter
    backtest_runner.py     # NEW: standalone OOS backtest orchestrator
    backtest_report.py     # NEW: consolidated report generation + consistency checks
scripts/
  run_backtest.py          # NEW: CLI to run backtest on trained model version
```

### Pattern 1: Standalone Backtest Runner (separation of training and validation)
**What:** A `BacktestRunner` class that loads a trained model version (from version dir), loads historical data, computes features, and runs per-window OOS backtesting using the `Backtester` with full cost modeling.
**When to use:** After training is complete, to validate the trained model independently.
**Why:** Currently, backtesting is embedded inside the training pipeline (step 7 in walk_forward.py). For BACK-01, we need out-of-sample validation that can be run independently of training, using saved models.

```python
# Conceptual pattern (not exact implementation)
class BacktestRunner:
    def __init__(self, version_dir: str, data: pd.DataFrame):
        # Load model, scaler, trade filter from version_dir
        # Load version.json for parameters
        pass

    def run_walk_forward_backtest(self) -> Dict[str, Any]:
        # Calculate walk-forward windows on the data
        # For each window's TEST portion:
        #   1. Scale features using saved scaler
        #   2. Generate predictions with saved model
        #   3. Apply trade filter (min_confidence, min_margin)
        #   4. Run Backtester.run_simple() with full costs
        #   5. Collect per-window metrics
        # Return per-window + aggregate results
        pass
```

### Pattern 2: Per-Window Metrics with Consistency Checks
**What:** Extract per-window backtest results and apply UAT consistency criteria.
**When to use:** After running walk-forward backtest, before declaring success.

```python
def check_consistency(window_results: List[Dict]) -> Dict[str, Any]:
    """Enforce BACK-04 criteria."""
    positive_windows = sum(1 for w in window_results if w["total_pips"] > 0)
    positive_pct = positive_windows / len(window_results)

    max_dd_violations = [
        w for w in window_results
        if w["max_drawdown_pct"] > 20.0
    ]

    return {
        "positive_window_pct": positive_pct,
        "passes_60pct_rule": positive_pct > 0.60,
        "max_dd_violations": len(max_dd_violations),
        "passes_20pct_dd_rule": len(max_dd_violations) == 0,
        "overall_pass": positive_pct > 0.60 and len(max_dd_violations) == 0,
    }
```

### Pattern 3: Reuse Existing Backtester (not rebuilding)
**What:** The `Backtester.run_simple()` method already handles ATR-based per-trade TP/SL with cost deductions. Extend it minimally for commission support.
**When to use:** Always. Do not create a new backtester class.

```python
# Extend Backtester.__init__ with:
commission_per_trade_pips: float = 0.0

# In run_simple(), adjust total_cost:
total_cost = self.spread_pips + self.slippage_pips + self.commission_per_trade_pips
```

### Anti-Patterns to Avoid
- **Rebuilding the backtester from scratch:** The existing `Backtester` already computes all required metrics. Extend, don't replace.
- **Coupling backtest validation to training:** BACK-01 requires out-of-sample validation. The backtest runner must work on saved models, not during training.
- **Using `AdvancedBacktester.run_reality_check()` for UAT:** It generates random volatility data when none is provided, which makes results non-deterministic. Use `Backtester.run_simple()` with ATR values instead.
- **Averaging per-window profit factors:** Already decided (STATE.md) to aggregate PF from total gross_profit / total gross_loss.
- **Computing drawdown in pips only:** The UAT says ">20% drawdown" which is percentage-based. The `Backtester._generate_report()` already computes `max_drawdown_pct`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Walk-forward windows | New window calculator | `calculate_walk_forward_windows()` from walk_forward.py | Already tested, handles edge cases, expanding windows |
| Equity curve + drawdown | Custom drawdown calc | `Backtester._generate_report()` | Already computes peak, drawdown USD and %, equity curve |
| Sharpe ratio | Custom Sharpe | `Backtester._generate_report()` already uses `sqrt(2600)` annualization | Matches project convention |
| Trade signal filtering | Custom threshold logic | `probs_to_trade_signals()` from trade_filter.py | Already handles confidence + margin gating |
| Feature scaling | New scaler | Load saved `feature_scaler.pkl` from version dir | Must use same scaler as training to avoid data leakage |
| Model loading | Custom pickle loader | Use model classes' `.load()` methods (XGBoostModel, LightGBMModel) | Handles version compatibility |

**Key insight:** This phase is about orchestration and reporting, not about building new calculation primitives. The numerical backbone (Backtester, ModelEvaluator, WalkForwardValidator) is already solid. The gap is in wiring them together for standalone OOS validation with a good report.

## Common Pitfalls

### Pitfall 1: Data Leakage in OOS Backtest
**What goes wrong:** Using the full dataset's scaler or features computed on full data for "out-of-sample" testing.
**Why it happens:** When loading a saved model, it's tempting to compute features on the entire dataset at once.
**How to avoid:** Load the scaler from the version directory (`feature_scaler.pkl`). It was fit on training data only (last window). For walk-forward validation, features can be computed on the full price data (technical indicators are causal/lookback-based), but the scaler must only be fit on the training portion.
**Warning signs:** OOS results significantly better than training results.

### Pitfall 2: Inconsistent TP/SL Between Training Labels and Backtest
**What goes wrong:** Training uses dynamic ATR-based TP/SL (default in ModelTrainer) but backtest uses fixed TP/SL.
**Why it happens:** The `version.json` stores `label_params` including `use_dynamic_atr`, `tp_atr_multiplier`, `sl_atr_multiplier`. If the backtest runner doesn't read and apply these, results are invalid.
**How to avoid:** Read `label_params` from `version.json` and configure the `Backtester` accordingly. Pass `atr_values` to `run_simple()` when dynamic ATR mode was used.
**Warning signs:** Backtest win rate dramatically different from training evaluation.

### Pitfall 3: Max Drawdown Percentage Calculation
**What goes wrong:** Computing drawdown as percentage of initial balance vs. percentage of peak balance.
**Why it happens:** Different conventions exist. The UAT says "no single window has >20% drawdown" but doesn't specify the base.
**How to avoid:** Use the existing `Backtester._generate_report()` which computes `max_dd_pct = max_drawdown / peak.max() * 100`. This is percentage of peak balance (standard convention).
**Warning signs:** Getting very different drawdown numbers than expected.

### Pitfall 4: Window Definition Mismatch
**What goes wrong:** Using different window boundaries for backtest validation than what was used during training.
**Why it happens:** Re-calculating windows with different parameters or different data length.
**How to avoid:** The `version.json` stores `walk_forward.windows` with exact train_start/train_end/test_start/test_end. Use these stored boundaries rather than re-calculating.
**Warning signs:** Window counts don't match between training report and backtest report.

### Pitfall 5: Commission Modeling for Capital.com CFDs
**What goes wrong:** Adding explicit commission costs when the broker doesn't charge separate commissions.
**Why it happens:** The UAT says "includes spread, slippage, commissions" but Capital.com charges via spread only (no separate commission for CFDs).
**How to avoid:** Add commission support to the Backtester for completeness (BACK-02 explicitly requires it), but default to 0. Document that Capital.com CFD costs are captured via the spread parameter.
**Warning signs:** Double-counting costs (spread already includes broker revenue).

### Pitfall 6: Empty Windows or Zero-Trade Windows
**What goes wrong:** Some walk-forward windows may produce zero trades (model predicts all HOLD), which breaks metric calculations and inflates "positive window" percentages.
**Why it happens:** Model may be very conservative, or confidence threshold too high.
**How to avoid:** Define "positive result" as either (a) total_pips > 0 or (b) zero-trade windows are counted as "neutral" not "positive". Zero-trade windows should be flagged separately in the report.
**Warning signs:** Report shows 100% positive windows but most have zero trades.

## Code Examples

### Loading a Trained Model Version for Backtest
```python
# From version.json, load model parameters
import json
import os

def load_version_config(version_dir: str) -> dict:
    with open(os.path.join(version_dir, "version.json"), "r") as f:
        return json.load(f)

config = load_version_config(version_dir)
feature_names = config["feature_names"]
label_params = config["label_params"]
use_dynamic_atr = label_params.get("use_dynamic_atr", False)
tp_atr_mult = label_params.get("tp_atr_multiplier", 2.0)
sl_atr_mult = label_params.get("sl_atr_multiplier", 1.5)
```

### Configuring Backtester With Commission Support
```python
# Existing Backtester, extended with commission
backtester = Backtester(
    initial_balance=10000.0,
    tp_pips=config["label_params"]["tp_pips"],
    sl_pips=config["label_params"]["sl_pips"],
    spread_pips=config["label_params"]["spread_pips"],
    slippage_pips=config["label_params"].get("slippage_pips", 0.5),
    # NEW: commission support
    # commission_per_trade_pips=0.0,  # Capital.com charges via spread
)
```

### Running Backtester.run_simple() with ATR Values
```python
# Already supported -- pass atr_values for dynamic TP/SL
report = backtester.run_simple(
    predictions=y_pred,        # from model
    actual_labels=y_test,      # true labels
    atr_values=atr_test,       # ATR values for test period
    tp_atr_multiplier=tp_atr_mult,
    sl_atr_multiplier=sl_atr_mult,
)
# report already contains: sharpe_ratio, max_drawdown_pct, win_rate, profit_factor
```

### Consistency Check Logic
```python
def validate_consistency(
    per_window_reports: list[dict],
) -> dict:
    """BACK-04: Check walk-forward consistency."""
    n_windows = len(per_window_reports)
    if n_windows == 0:
        return {"overall_pass": False, "reason": "No windows"}

    # Positive windows: total_pips > 0 (exclude zero-trade windows)
    windows_with_trades = [w for w in per_window_reports if w["n_trades"] > 0]
    positive = sum(1 for w in windows_with_trades if w["total_pips"] > 0)
    positive_pct = positive / len(windows_with_trades) if windows_with_trades else 0

    # Max drawdown per window (percentage)
    dd_violations = [
        w for w in per_window_reports
        if w["max_drawdown_pct"] > 20.0
    ]

    return {
        "n_windows": n_windows,
        "windows_with_trades": len(windows_with_trades),
        "positive_windows": positive,
        "positive_pct": positive_pct,
        "passes_60pct": positive_pct > 0.60,
        "dd_violations": len(dd_violations),
        "passes_20pct_dd": len(dd_violations) == 0,
        "overall_pass": positive_pct > 0.60 and len(dd_violations) == 0,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed 50/30 pip TP/SL | ATR-based dynamic TP/SL | Phase 4 (just completed) | Backtest must use `atr_values` parameter |
| Simple train/test split | Walk-forward expanding windows | Phase 2 | OOS validation already built into training |
| XGBoost gain importance | SHAP-based feature pruning | Phase 3 | Models may have different feature sets per version |
| Averaged profit factors | Aggregate PF from totals | Phase 2 decision | Already implemented in `generate_training_report()` |

**Already completed (do not rebuild):**
- Walk-forward window calculation (`calculate_walk_forward_windows`)
- Expanding (anchored) windows with purge gap
- Per-window scaler fitting (TRAIN-02)
- Backtester with spread + slippage deduction
- Sharpe annualized with `sqrt(2600)`
- Equity curve and drawdown calculation
- Grade assignment (EXCELLENT/GOOD/ACCEPTABLE/WEAK/UNUSABLE)

## Gap Analysis: What Exists vs. What's Needed

### Already Done (reuse directly)
| Capability | Location | Status |
|-----------|----------|--------|
| Walk-forward windows | `walk_forward.py` | Complete, tested |
| Backtester with spread/slippage | `backtester.py` | Complete |
| ATR-based per-trade TP/SL in backtester | `backtester.py:run_simple()` | Complete |
| Sharpe ratio calculation | `backtester.py:_generate_report()` | Complete |
| Max drawdown USD + % | `backtester.py:_generate_report()` | Complete |
| Win rate, profit factor | `backtester.py:_generate_report()` | Complete |
| Model versioning + version.json | `model_versioning.py` | Complete |
| Feature scaler save/load | `feature_scaler.py` | Complete |
| Trade filter (confidence/margin gating) | `trade_filter.py` | Complete |
| Training report JSON | `walk_forward.py:generate_training_report()` | Complete |

### Needs Building (Phase 5 work)
| Capability | Requirement | Effort |
|-----------|------------|--------|
| Commission parameter in Backtester | BACK-02 | Small: add `commission_per_trade_pips` to `__init__`, include in `total_cost_pips` |
| Standalone backtest runner | BACK-01 | Medium: new class that loads model + runs OOS backtest independently of training |
| Consolidated backtest report | BACK-03 | Medium: per-window + aggregate report with all UAT metrics in one view |
| Per-window consistency checks | BACK-04 | Small: >60% positive windows, no window >20% drawdown |
| Backtest CLI script | BACK-01 | Small: `scripts/run_backtest.py` to run backtest from command line |
| Equity curve visualization | BACK-03 (nice to have) | Small: matplotlib chart of per-window equity curves |

## Open Questions

1. **Should the backtest re-run walk-forward training or just evaluate saved models?**
   - What we know: Training already evaluates each window. But BACK-01 says "validates strategy on out-of-sample data" which implies a separate evaluation pass.
   - What's unclear: Whether "out-of-sample" means (a) the test portions of walk-forward windows (already done in training) or (b) entirely separate data not used in training at all.
   - Recommendation: Use approach (a) -- the walk-forward test windows ARE out-of-sample data. The backtest runner should re-run predictions on these OOS windows using the saved model, with full cost modeling. This is both simpler and more rigorous than finding new data.

2. **How should zero-trade windows be counted for the 60% rule?**
   - What we know: Some windows may produce zero trades if the model is conservative.
   - What's unclear: Should zero-trade windows count as "positive" (no losses), "negative" (no profits), or be excluded?
   - Recommendation: Exclude zero-trade windows from the 60% calculation but flag them separately. A strategy that produces no trades is not useful, but it shouldn't be penalized as "negative."

3. **Per-window drawdown base: initial balance or per-window starting balance?**
   - What we know: UAT says "no single window has >20% drawdown." The `Backtester` computes drawdown as % of peak balance.
   - What's unclear: Each window starts fresh (reset balance) or continues from previous window's ending balance.
   - Recommendation: Each window is an independent backtest with `initial_balance=10000`. This isolates per-window performance and makes the 20% threshold meaningful. Reset equity for each window.

## Sources

### Primary (HIGH confidence)
- Direct code review of `ai_engine/training/backtester.py` -- full Backtester implementation
- Direct code review of `ai_engine/training/walk_forward.py` -- WalkForwardValidator, window calculation
- Direct code review of `ai_engine/training/evaluation.py` -- ModelEvaluator with all metrics
- Direct code review of `ai_engine/training/pipeline.py` -- TrainingPipeline integration
- Direct code review of `ai_engine/training/trainer.py` -- ModelTrainer with all parameters
- Direct code review of `strategy/backtesting/advanced_backtester.py` -- AdvancedBacktester
- Direct code review of `strategy/regime_detector.py` -- RegimeDetector
- Direct code review of `strategy/regime_params.py` -- REGIME_PARAMS
- `.planning/REQUIREMENTS.md` -- BACK-01 through BACK-04 definitions
- `.planning/STATE.md` -- All prior decisions (aggregate PF, Sharpe sqrt(2600), etc.)

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` -- Phase 5 scope and UAT criteria

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries needed, all code reviewed
- Architecture: HIGH - clear gap analysis from existing code, straightforward extension
- Pitfalls: HIGH - identified from actual code patterns and prior project decisions
- Gap analysis: HIGH - based on line-by-line code review of every relevant file

**Research date:** 2026-03-08
**Valid until:** 2026-04-08 (stable -- no external dependency changes expected)
