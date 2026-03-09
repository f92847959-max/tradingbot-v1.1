# Phase 2: Training Pipeline -- Walk-Forward Validation - Research

**Researched:** 2026-03-06
**Domain:** Walk-forward validation for ML trading systems (XGBoost/LightGBM)
**Confidence:** HIGH

## Summary

This phase replaces the single chronological split (70/15/15) in `pipeline.py` with walk-forward validation, adds model versioning so each training run is preserved, generates a training report showing metrics across all windows, and enforces minimum 6 months of data. The existing 12-step pipeline in `TrainingPipeline.run()` (333 lines) is the primary modification target.

The key architectural challenge is restructuring the pipeline so that steps 6-11 (split, scale, train, evaluate) execute inside a loop over walk-forward windows, while steps 1-5 (data validation, indicator computation, label generation, warmup removal, feature/label separation) remain outside the loop. This is because technical indicators (EMA-200, RSI-14) require full lookback history to compute correctly -- computing them per-window would lose warmup data and produce incorrect values.

**Primary recommendation:** Use anchored (expanding) windows with a sliding test period. Compute base indicators on full data before the loop. Recompute feature scaling per window. Save each window's model artifacts in a versioned directory structure.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Window count: **Automatic/dynamic** -- determine number of windows programmatically based on available data and logical constraints (not a fixed hardcoded number)
- Test period per window: **Proportional at 20% of window size**
- Success metrics: **All key metrics combined** -- show Profit Factor, Win Rate, Expectancy (pips), plus standard ML metrics per window. No single metric decides; user reviews full picture.
- Existing purging gap logic must be preserved within each walk-forward window
- Feature scaler must be fit per-window on training data only
- Current label parameters (TP: 1500 pips, SL: 800 pips, spread: 2.5, slippage: 0.5) remain unchanged
- The existing `model_metadata.json` format should be extended, not replaced

### Claude's Discretion
- Window type (expanding vs sliding): research-based recommendation
- Feature computation per window: research-based recommendation
- Directory structure for versioned models on disk
- Production model selection strategy (symlink, config pointer, etc.)
- Retention policy for old versions
- Report format (JSON, HTML, console, combination)
- Internal implementation details of the walk-forward loop
- How to integrate with existing 12-step pipeline (modify in-place vs wrapper)
- Error handling for windows with insufficient data
- Whether to parallelize window training
- How to handle the purging gap within walk-forward context
- Trade filter tuning: per-window or on aggregated results

### Deferred Ideas (OUT OF SCOPE)
None -- phase scope is well-defined by requirements TRAIN-01, TRAIN-02, TRAIN-05, TRAIN-06, TRAIN-07.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRAIN-01 | Walk-forward validation replaces simple chronological split | Core architecture: walk-forward loop with expanding windows, dynamic window count, 20% test ratio |
| TRAIN-02 | Features are computed AFTER train/test split to prevent data leakage | Feature scaler fit per-window; base indicators computed on full data (safe); derived features recomputed per window |
| TRAIN-05 | Model versioning -- each training run saves version metadata (date, params, metrics) | Versioned directory structure with version.json per run |
| TRAIN-06 | Training report shows walk-forward results across all windows | JSON + console report with per-window and aggregate metrics |
| TRAIN-07 | Minimum 6 months of historical data used for training | Data validation check at pipeline start based on index timestamps |
</phase_requirements>

## Architecture Patterns

### Walk-Forward Window Design: Expanding (Anchored) Windows

**Recommendation: Use expanding (anchored) windows, not sliding.**

Rationale for gold intraday trading with XGBoost/LightGBM:
1. **More training data per window** -- tree-based models (XGBoost, LightGBM) benefit from more data and are resistant to irrelevant old data because they learn splits, not weights. Unlike neural networks, they do not suffer from "forgetting" and handle distributional shift gracefully.
2. **Stability** -- expanding windows produce more stable results because each window has a superset of the previous window's training data. Sliding windows can produce erratic results when small windows exclude important market regimes.
3. **Practical for this dataset** -- the system uses 5-minute candles fetched from Capital.com. With limited history (likely 1-2 years), sliding windows would produce very small training sets. Expanding windows maximize data usage.
4. **Industry standard for ML models** -- the QuantInsti and Alpha Scientist references confirm that anchored/expanding windows are standard for ML-based trading systems, while sliding windows are more common for traditional rule-based strategy optimization.

**Window structure:**
```
Full data timeline: [======================================================]

Window 1: [TRAIN============]  gap  [TEST==]
Window 2: [TRAIN====================]  gap  [TEST==]
Window 3: [TRAIN============================]  gap  [TEST==]
Window 4: [TRAIN====================================]  gap  [TEST==]
Window 5: [TRAIN============================================]  gap  [TEST==]
```

### Dynamic Window Count Algorithm

The user locked "automatic/dynamic" window count with "20% of window size" for test period. Algorithm:

```python
def calculate_windows(n_samples: int, min_train_samples: int = 2000) -> List[WindowSpec]:
    """
    Dynamically determine walk-forward windows.

    Strategy: Start with minimum viable training set,
    step forward by test_size each window.
    Test size = 20% of total window size (train + test).

    For window with train_size T: test_size = T * 0.25
    (because test = 20% of total means test = 25% of train)
    """
    windows = []
    # First window: minimum training size
    train_end = min_train_samples

    while train_end < n_samples:
        train_size = train_end
        test_size = max(int(train_size * 0.25), 200)  # 20% of total = 25% of train
        test_end = min(train_end + purge_gap + test_size, n_samples)

        if test_end - train_end - purge_gap < 100:  # Too few test samples
            break

        windows.append(WindowSpec(
            train_start=0,  # Anchored/expanding
            train_end=train_end,
            test_start=train_end + purge_gap,
            test_end=test_end,
        ))
        train_end = test_end  # Next window starts training up to where test ended

    return windows
```

This guarantees at least 5 windows for typical datasets (10,000+ candles) and adapts to available data.

### Feature Computation Strategy: Compute Indicators Once, Scale Per Window

**Recommendation: Compute base indicators on full data ONCE, then fit scaler per window.**

This is the critical data leakage question. Analysis of the codebase shows a two-layer architecture:

1. **Layer 1 -- Base indicators** (`market_data/indicators.py`): Uses `pandas_ta` to compute RSI-14, EMA-9/21/50/200, MACD, ADX, Stochastic, etc. These are purely lookback-based (each value depends only on past OHLCV). Computing them on the full dataset does NOT leak future information.

2. **Layer 2 -- Derived features** (`ai_engine/features/`): Computes zones, crosses, distances from base indicators. These are also point-in-time (e.g., "is RSI > 70?" at each candle). No leakage.

3. **Layer 3 -- Feature scaling** (`FeatureScaler`): StandardScaler computes mean/std. This MUST be fit only on training data per window. The current code already does this correctly.

**Why NOT recompute indicators per window:**
- EMA-200 requires 200 candles of warmup. Recomputing on a window slice would waste 200 candles or produce different values for the initial candles.
- RSI-14 uses an exponential smoothing that converges over ~100 bars. Computing on a slice changes early values.
- All these indicators are purely lookback-based, so computing them on full data is NOT leakage.
- The existing pipeline already computes features in step 2 (before split in step 6). This is correct and should remain.

**What MUST be per-window:**
- Feature scaler (StandardScaler) -- fit on window's training data only (TRAIN-02)
- Feature selection (importance threshold) -- per window to avoid using test-period importance
- Trade filter tuning -- per window's validation subset

### Recommended Project Structure Changes

```
ai_engine/
  training/
    pipeline.py          # Modified: walk-forward loop wrapping steps 6-11
    walk_forward.py      # NEW: WalkForwardValidator class (window calculation, reporting)
    data_preparation.py  # Minor: add data duration validation
    trainer.py           # Minor: pass versioning params
  saved_models/
    latest/              # Symlink or copy of best version (production pointer)
    v001_20260306_143022/  # Versioned model directory
      xgboost_gold.pkl
      lightgbm_gold.pkl
      feature_scaler.pkl
      version.json       # Training metadata + walk-forward results
    v002_20260307_091500/
      ...
```

### Pipeline Integration: Modify In-Place with Walk-Forward Wrapper

**Recommendation: Refactor `TrainingPipeline.run()` to extract a `_train_single_window()` method, then wrap it in a walk-forward loop.**

Current flow (steps 1-12, sequential):
```
1. Validate -> 2. Features -> 3. Labels -> 4. Warmup -> 5. Split X/y
-> 6. Chrono split -> 7. Scale -> 8-9. Train -> 10. ML eval -> 11. Trade eval -> 12. Save
```

New flow:
```
1. Validate (+ 6-month check) -> 2. Features -> 3. Labels -> 4. Warmup -> 5. Split X/y
-> WALK-FORWARD LOOP:
   for each window:
     6. Window split (with purge gap)
     7. Scale (fit on window train)
     8-9. Train XGBoost + LightGBM
     10. ML eval on window test
     11. Trade eval on window test
     Collect per-window results
-> 12. Save final models (last window) + version.json + report
```

### Anti-Patterns to Avoid
- **Computing indicators per window:** Wastes warmup data, changes indicator values for early candles, adds computational cost with zero benefit for lookback-only indicators.
- **Using the same scaler across windows:** Violates TRAIN-02. Each window must fit its own scaler on its training portion.
- **Fixed window count:** User explicitly locked "automatic/dynamic." Hardcoding 5 or 10 windows violates the constraint.
- **Shuffling within windows:** Time series must remain chronological. Never randomize order.
- **Overlapping test periods:** Each test period must be strictly after the previous one's test period ends. No data point should appear in two different test sets.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature scaling | Custom mean/std normalization | Existing `FeatureScaler` (wraps sklearn) | Already handles fit/transform correctly |
| Model serialization | Custom pickle/json export | Existing `.save()` methods on XGBoost/LightGBM models | Already implemented and tested |
| Trading metrics | Custom win rate / PF calculation | Existing `ModelEvaluator.evaluate_trading()` | Handles edge cases (zero trades, division by zero) |
| Trade filter tuning | New grid search | Existing `tune_trade_filter()` in `trade_filter.py` | Already integrated with evaluator |
| Technical indicators | Per-window indicator computation | Existing `calculate_indicators()` on full data | Lookback-only, no leakage, avoids warmup waste |

**Key insight:** Most of the per-window logic is already in the existing pipeline steps 6-11. The task is restructuring the flow, not rebuilding computation.

## Common Pitfalls

### Pitfall 1: Indicator Leakage Confusion
**What goes wrong:** Developers recompute indicators per window "to prevent leakage," which produces incorrect indicator values for early candles in each window (missing warmup) and wastes data.
**Why it happens:** Confusing "lookback indicators" (safe to compute on full data) with "future-looking normalization" (must be per-window).
**How to avoid:** Only the scaler and feature selection need per-window treatment. Indicators and derived features are lookback-only and safe on full data.
**Warning signs:** If first 200 candles of each window have NaN features, indicators are being recomputed per window.

### Pitfall 2: Purge Gap Inconsistency
**What goes wrong:** Labels at the boundary between train and test sets overlap due to the Triple Barrier method's forward-looking max_candles parameter.
**Why it happens:** The purge gap must account for `max_candles` (currently 60 5-minute candles = 5 hours). If the gap is too small, train labels "see" test-period prices.
**How to avoid:** Keep the existing dynamic purge gap calculation: `min(max_label_horizon, max(8, len(X) // 20))`. Apply it between train_end and test_start in each window.
**Warning signs:** If test results are suspiciously good on the first window and degrade on later windows.

### Pitfall 3: Test Period Overlap Between Windows
**What goes wrong:** Data points appear in multiple test periods, inflating the effective out-of-sample evaluation.
**Why it happens:** Windows not stepped forward correctly.
**How to avoid:** Each window's test_start must be >= previous window's test_end. With expanding windows, the train portion grows, but test periods must be sequential and non-overlapping.

### Pitfall 4: Too Few Samples Per Window
**What goes wrong:** Windows with < 200 test samples produce unreliable metrics (high variance in win rate, profit factor).
**Why it happens:** Over-splitting available data into too many windows.
**How to avoid:** Set minimum test size (200 samples) and skip/merge windows that don't meet it. Log a warning when a window has fewer than expected samples.

### Pitfall 5: Model Versioning Overwriting
**What goes wrong:** New training run overwrites the production model, breaking live trading.
**Why it happens:** Current code saves to fixed paths (`xgboost_gold.pkl`, `model_metadata.json`).
**How to avoid:** Save to versioned directories. Maintain a `latest/` pointer that is only updated when training succeeds.

### Pitfall 6: Report Aggregation Error
**What goes wrong:** Averaging profit factors or Sharpe ratios across windows instead of computing them from aggregated trade results.
**Why it happens:** Treating ratios as additive.
**How to avoid:** Collect all trades from all windows, then compute aggregate PF/Sharpe from the combined set. Report per-window metrics separately.

## Code Examples

### Walk-Forward Window Calculation

```python
from dataclasses import dataclass
from typing import List

@dataclass
class WindowSpec:
    """Specification for a single walk-forward window."""
    window_id: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int

    @property
    def train_size(self) -> int:
        return self.train_end - self.train_start

    @property
    def test_size(self) -> int:
        return self.test_end - self.test_start


def calculate_walk_forward_windows(
    n_samples: int,
    min_train_samples: int = 2000,
    purge_gap: int = 60,
    min_test_samples: int = 200,
) -> List[WindowSpec]:
    """
    Calculate expanding walk-forward windows dynamically.

    Test period = 20% of total window size (= 25% of train size).
    Windows are non-overlapping in test period.
    Training always starts from index 0 (expanding/anchored).
    """
    windows = []
    train_end = min_train_samples
    window_id = 0

    while train_end < n_samples:
        test_size = max(int(train_end * 0.25), min_test_samples)
        test_start = train_end + purge_gap
        test_end = min(test_start + test_size, n_samples)

        actual_test_size = test_end - test_start
        if actual_test_size < min_test_samples:
            break  # Not enough data for a valid test period

        windows.append(WindowSpec(
            window_id=window_id,
            train_start=0,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
        ))

        window_id += 1
        train_end = test_end  # Next window trains up to end of this test

    return windows
```

### Version Directory Creation

```python
import os
from datetime import datetime

def create_version_dir(base_dir: str) -> str:
    """Create a new versioned model directory.

    Format: v{NNN}_{YYYYMMDD}_{HHMMSS}
    """
    existing = [d for d in os.listdir(base_dir)
                if os.path.isdir(os.path.join(base_dir, d)) and d.startswith("v")]

    if existing:
        max_num = max(int(d.split("_")[0][1:]) for d in existing)
        next_num = max_num + 1
    else:
        next_num = 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_name = f"v{next_num:03d}_{timestamp}"
    version_dir = os.path.join(base_dir, version_name)
    os.makedirs(version_dir, exist_ok=True)
    return version_dir
```

### Version JSON Schema

```python
version_json = {
    "version": "v001",
    "training_date": "2026-03-06T14:30:22",
    "training_duration_seconds": 45.2,
    "timeframe": "5m",
    "data_range": {
        "start": "2025-01-01T00:00:00Z",
        "end": "2026-03-06T00:00:00Z",
        "n_candles": 12000,
        "months_of_data": 14.2,
    },
    "walk_forward": {
        "n_windows": 6,
        "window_type": "expanding",
        "purge_gap_candles": 60,
        "windows": [
            {
                "window_id": 0,
                "train_samples": 2000,
                "test_samples": 500,
                "metrics": {
                    "xgboost": {"accuracy": 0.55, "f1": 0.52, "win_rate": 0.58, "profit_factor": 1.4, "expectancy": 2.3},
                    "lightgbm": {"accuracy": 0.57, "f1": 0.54, "win_rate": 0.60, "profit_factor": 1.6, "expectancy": 3.1},
                },
            },
            # ... more windows
        ],
    },
    "aggregate_metrics": {
        "xgboost": {"win_rate": 0.56, "profit_factor": 1.35, "expectancy": 1.8, "sharpe": 1.2, "n_trades": 450},
        "lightgbm": {"win_rate": 0.59, "profit_factor": 1.52, "expectancy": 2.5, "sharpe": 1.5, "n_trades": 520},
    },
    "label_params": {"tp_pips": 1500.0, "sl_pips": 800.0, "spread_pips": 2.5, "slippage_pips": 0.5},
    "n_features_original": 60,
    "n_features_selected": 14,
    "feature_names": ["..."],
    "best_model": "lightgbm",
    "production_ready": True,
}
```

### Minimum 6-Month Data Validation

```python
def validate_minimum_data(df: pd.DataFrame, min_months: int = 6) -> None:
    """Validate that DataFrame contains at least min_months of data."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must have DatetimeIndex for duration check")

    duration = df.index[-1] - df.index[0]
    months = duration.days / 30.44  # Average days per month

    if months < min_months:
        raise ValueError(
            f"Insufficient data: {months:.1f} months available, "
            f"minimum {min_months} months required. "
            f"Date range: {df.index[0]} to {df.index[-1]}"
        )
```

### Training Report (JSON + Console)

```python
def generate_training_report(
    windows_results: List[Dict],
    aggregate_metrics: Dict,
    version_info: Dict,
) -> Dict:
    """Generate walk-forward training report.

    Returns dict suitable for JSON serialization.
    Also logs a console-friendly summary.
    """
    report = {
        "report_date": datetime.now().isoformat(),
        "version": version_info["version"],
        "summary": {
            "n_windows": len(windows_results),
            "total_test_samples": sum(w["test_samples"] for w in windows_results),
            "best_model": aggregate_metrics.get("best_model"),
        },
        "per_window": windows_results,
        "aggregate": aggregate_metrics,
    }

    # Console output
    logger.info("=" * 70)
    logger.info("WALK-FORWARD TRAINING REPORT")
    logger.info("=" * 70)
    logger.info(f"Windows: {len(windows_results)}")
    for w in windows_results:
        logger.info(
            f"  Window {w['window_id']}: "
            f"train={w['train_samples']}, test={w['test_samples']} | "
            f"WR={w['metrics']['win_rate']:.1%} PF={w['metrics']['profit_factor']:.2f} "
            f"Exp={w['metrics']['expectancy']:.1f}pips"
        )
    logger.info("-" * 70)
    logger.info("AGGREGATE:")
    for model, metrics in aggregate_metrics.items():
        if isinstance(metrics, dict):
            logger.info(
                f"  {model}: WR={metrics.get('win_rate', 0):.1%} "
                f"PF={metrics.get('profit_factor', 0):.2f} "
                f"Exp={metrics.get('expectancy', 0):.1f}pips "
                f"Sharpe={metrics.get('sharpe', 0):.2f}"
            )

    return report
```

### Production Model Pointer

```python
def update_production_pointer(base_dir: str, version_dir: str) -> None:
    """Update the 'latest' pointer to the new version.

    Uses a JSON file (not symlink) for Windows compatibility.
    """
    pointer_path = os.path.join(base_dir, "production.json")
    pointer = {
        "version_dir": os.path.basename(version_dir),
        "updated": datetime.now().isoformat(),
        "path": version_dir,
    }
    with open(pointer_path, "w") as f:
        json.dump(pointer, f, indent=2)

    # Also copy models to base dir for backward compatibility
    for filename in ["xgboost_gold.pkl", "lightgbm_gold.pkl", "feature_scaler.pkl"]:
        src = os.path.join(version_dir, filename)
        dst = os.path.join(base_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
```

## Discretionary Recommendations

### Trade Filter Tuning: Per-Window with Aggregated Final Selection
Tune trade filter per-window to get per-window metrics, but select the final production filter by running tuning on the last window's validation subset. This balances adaptiveness with stability.

### Report Format: JSON + Console
JSON for machine readability and downstream use by control app (CTRL-05). Console output for immediate developer feedback during training. No HTML needed -- the control app can render the JSON later.

### Retention Policy: Keep Last 5 Versions
Simple and practical. Delete versions older than the 5th most recent at the end of each training run. This covers typical iteration cycles without filling disk.

### Parallelization: Do Not Parallelize
The windows are computed sequentially by nature (expanding). Each window trains 2 models (XGBoost + LightGBM) which already use multi-core internally. Parallelizing windows would compete for CPU cores and increase memory usage. Keep it sequential.

### Production Model Selection: Use Last Window's Models
The last walk-forward window has the most training data and the most recent test period. Use its trained models as the production model. Store all per-window metrics in version.json for analysis.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single 70/15/15 split | Walk-forward validation (expanding) | Standard since ~2015 | Prevents overfitting, gives realistic performance estimate |
| Fixed model save path | Versioned model directories | ML ops standard | Preserves history, enables rollback |
| Manual data validation | Automated minimum data checks | Best practice | Prevents training on insufficient data |

## Open Questions

1. **How much data does the Capital.com API provide?**
   - What we know: The current metadata shows 800 raw candles, which is quite small for walk-forward with 5+ windows
   - What's unclear: Maximum historical data available via the broker API
   - Recommendation: Support `--count` flag in train script for larger fetches. Also support CSV input for longer history. Set `min_train_samples=1500` (not 2000) to accommodate smaller datasets, and allow minimum 3 windows instead of 5 if data is limited.

2. **Backward compatibility of model loading**
   - What we know: The live trading system loads from fixed paths (`ai_engine/saved_models/xgboost_gold.pkl`)
   - What's unclear: How many places reference these fixed paths
   - Recommendation: Copy production models to the base directory (backward compat) AND save to versioned directory. This way existing code works unchanged.

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `ai_engine/training/pipeline.py` (333 lines, full 12-step pipeline)
- Codebase analysis: `ai_engine/training/data_preparation.py` (split_chronological with purge gap)
- Codebase analysis: `ai_engine/training/evaluation.py` (ML + trading metrics)
- Codebase analysis: `market_data/indicators.py` (pandas_ta lookback indicators)
- Codebase analysis: `ai_engine/features/feature_engineer.py` (derived features from indicators)
- Codebase analysis: `ai_engine/saved_models/model_metadata.json` (current metadata format)

### Secondary (MEDIUM confidence)
- [QuantInsti: Walk-Forward Optimization](https://blog.quantinsti.com/walk-forward-optimization-introduction/) -- expanding vs sliding window comparison
- [Interactive Brokers: Deep Dive into Walk Forward Analysis](https://www.interactivebrokers.com/campus/ibkr-quant-news/the-future-of-backtesting-a-deep-dive-into-walk-forward-analysis/) -- WFA as gold standard
- [Unger Academy: Walk Forward Analysis](https://ungeracademy.com/posts/how-to-use-walk-forward-analysis-you-may-be-doing-it-wrong) -- anchored vs rolling comparison
- [Alpha Scientist: Walk-Forward Model Building](https://alphascientist.com/walk_forward_model_building.html) -- ML-specific walk-forward
- [AmiBroker: Walk-Forward Testing](https://www.amibroker.com/guide/h_walkforward.html) -- intraday boundary handling
- [Build Alpha: Robustness Testing Guide](https://www.buildalpha.com/robustness-testing-guide/) -- data leakage with rolling indicators

### Tertiary (LOW confidence)
- None -- all findings verified with codebase or multiple sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- using existing libraries (XGBoost, LightGBM, pandas_ta, sklearn), no new dependencies
- Architecture: HIGH -- clear restructuring path from existing pipeline, well-understood walk-forward pattern
- Pitfalls: HIGH -- data leakage and purge gap concerns verified against actual codebase structure
- Feature computation: HIGH -- verified that indicators are lookback-only by reading `market_data/indicators.py`

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable domain, no fast-moving dependencies)
