# Phase 2: Training Pipeline — Walk-Forward Validation - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the current single static chronological split (70/15/15) with walk-forward validation. Add model versioning so each training run is preserved with metadata. Generate a training report showing metrics across all walk-forward windows. Enforce minimum 6 months of historical data.

**What exists (from Phase 1):**
- 12-step training pipeline in `ai_engine/training/pipeline.py` (333 lines)
- Chronological split with purging gap in `data_preparation.py`
- Triple Barrier labeling with realistic costs in `label_generator.py`
- Feature engineering (~60 features) in `ai_engine/features/feature_engineer.py`
- XGBoost + LightGBM ensemble training
- Feature scaler fit only on training data
- Basic metadata saved as `model_metadata.json` (overwrites each run)
- Train script at `scripts/train_models.py`

**What this phase changes:**
- Pipeline step 6 (single split) becomes walk-forward loop
- Model saving becomes versioned (multiple runs preserved)
- New training report generated after walk-forward completes
- Data validation enforces minimum 6 months

</domain>

<decisions>
## Implementation Decisions

### Walk-Forward Window Design
- Window type (expanding vs sliding): Claude's discretion based on research — pick what works best for gold intraday trading
- Window count: **Automatic/dynamic** — determine number of windows programmatically based on available data and logical constraints (not a fixed hardcoded number)
- Test period per window: **Proportional at 20% of window size**
- Feature computation per window (recompute vs compute-once): Claude's discretion based on research — determine if recomputing indicators per window matters for RSI/EMA-type features

### Model Versioning
- Directory structure on disk: Claude's discretion — pick the most practical approach for this codebase
- Production model selection: Claude's discretion — implement whatever strategy is best (symlink, config pointer, etc.)
- Retention policy for old versions: Claude's discretion

### Training Report
- Report format (JSON, HTML, console, combination): Claude's discretion — fit with existing codebase patterns
- Success metrics: **All key metrics combined** — show Profit Factor, Win Rate, Expectancy (pips), plus standard ML metrics per window. No single metric decides; user reviews full picture.

### Claude's Discretion
- Internal implementation details of the walk-forward loop
- How to integrate with existing 12-step pipeline (modify in-place vs wrapper)
- Error handling for windows with insufficient data
- Whether to parallelize window training
- How to handle the purging gap within walk-forward context

</decisions>

<specifics>
## Specific Ideas

- The existing purging gap logic in `data_preparation.py` (lines 51-103) should be preserved within each walk-forward window
- Feature scaler must be fit per-window on training data only (current behavior, extend to walk-forward)
- Trade filter tuning (grid search over confidence/margin) should run per-window or on aggregated results — Claude decides
- The existing `model_metadata.json` format should be extended, not replaced
- Current label parameters (TP: 1500 pips, SL: 800 pips, spread: 2.5, slippage: 0.5) remain unchanged

</specifics>

<deferred>
## Deferred Ideas

None — phase scope is well-defined by requirements TRAIN-01, TRAIN-02, TRAIN-05, TRAIN-06, TRAIN-07.

</deferred>

---
*Phase: 02-training-pipeline-walk-forward-validation*
*Context gathered: 2026-03-06 via discuss-phase*
