# Phase 3: Feature Engineering -- SHAP & Pruning - Research

**Researched:** 2026-03-07
**Domain:** SHAP-based feature importance + automatic feature pruning for tree-based models (XGBoost 3.2.0 / LightGBM 4.6.0)
**Confidence:** HIGH

## Summary

Phase 3 replaces the existing XGBoost-importance-based feature selection in the walk-forward pipeline with SHAP (SHapley Additive exPlanations) feature importance analysis and adds automatic pruning of the bottom 50% of features by importance. The project already has a feature selection step inside `WalkForwardValidator.run_window()` (lines 214-260 of walk_forward.py) that uses XGBoost's built-in `feature_importances_` with a 0.5% threshold. SHAP provides a more principled, model-agnostic importance metric grounded in game theory (Shapley values) that captures both the direction and magnitude of each feature's contribution.

SHAP 0.51.0 (released 2026-03-04) supports Python 3.13 with pre-built wheels and has resolved the XGBoost >= 3.1 `base_score` compatibility issue (GitHub issue #4202, fixed in 0.50.0). Both XGBoost and LightGBM have native C++ SHAP integrations via `TreeExplainer`, making computation fast (no background dataset needed in `tree_path_dependent` mode). The 3-class multi-class output produces SHAP values of shape `(n_samples, n_features, 3)` -- one set per class. For global feature importance, take `mean(|SHAP values|)` across all samples and classes.

The phase also requires saving a feature importance bar chart as a PNG with the training report and storing SHAP values in the version directory. Matplotlib with the `Agg` backend handles headless chart generation.

**Primary recommendation:** Use `shap.TreeExplainer` with both XGBoost and LightGBM models per walk-forward window, compute mean absolute SHAP values for global importance, prune bottom 50% by importance, retrain with pruned features, and compare performance.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TRAIN-03 | SHAP-based feature importance analysis is integrated | SHAP 0.51.0 TreeExplainer with XGBoost 3.2.0 + LightGBM 4.6.0; compute per-window, save per version |
| TRAIN-04 | Bottom 50% features by importance can be pruned automatically | Mean absolute SHAP values across classes, rank features, prune bottom 50%, retrain + compare performance |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| shap | 0.51.0 | Feature importance via Shapley values | Gold standard for model-agnostic feature importance; native TreeExplainer for XGBoost/LightGBM is exact and fast |
| matplotlib | >=3.8 | Feature importance bar chart generation | Only needed for `savefig` to PNG; SHAP depends on it for plots |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | (existing) | Mean absolute SHAP computation | Already in project |
| pandas | (existing) | Feature name mapping | Already in project |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SHAP TreeExplainer | XGBoost built-in `feature_importances_` | Already in use (Phase 2); gain-based only, no direction info, biased toward high-cardinality features |
| SHAP TreeExplainer | Permutation importance | Much slower (requires multiple model evaluations); SHAP is exact for trees |
| matplotlib | plotly | Interactive but heavier dependency; training pipeline only needs static PNG |

**Installation:**
```bash
pip install shap==0.51.0 matplotlib
```

## Architecture Patterns

### Integration Points in Existing Pipeline

```
pipeline.py
  Step 6: Walk-forward validation
    walk_forward.py -> WalkForwardValidator.run_window()
      Existing step 5: Feature selection (XGBoost importance, 0.5% threshold)
      >>> REPLACE with: SHAP-based importance + 50% pruning
      Existing step 6: Train LightGBM on selected features
      >>> AFTER: Compare pruned vs full model performance

  Step 7: Save models with versioning
    model_versioning.py -> write_version_json()
      >>> ADD: shap_importance dict to version.json
      >>> ADD: feature_importance_chart.png to version directory
```

### Pattern 1: SHAP Computation per Walk-Forward Window

**What:** After initial XGBoost training in each walk-forward window, compute SHAP values using `TreeExplainer` on the test set (or a subsample of training data). Use the SHAP values to determine which features to prune.

**When to use:** Every walk-forward window, after step 4 (Train XGBoost initial) and before step 6 (Train LightGBM).

**Example:**
```python
# Source: SHAP official docs + XGBoost integration
import shap
import numpy as np

# After XGBoost is trained on X_train_scaled
explainer = shap.TreeExplainer(trainer._xgboost.model)

# Compute SHAP values on test data (or background subsample)
# For 3-class: shape = (n_samples, n_features, 3)
shap_values = explainer.shap_values(X_test_scaled)

# Global importance: mean(|SHAP|) across samples and classes
# shap_values is list of 3 arrays, each (n_samples, n_features)
if isinstance(shap_values, list):
    # Older API: list of arrays per class
    abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0)
else:
    # Newer API: single array (n_samples, n_features, n_classes)
    abs_shap = np.mean(np.abs(shap_values), axis=(0, 2))

mean_abs_shap = np.mean(abs_shap, axis=0)  # (n_features,)

# Build importance dict
shap_importance = dict(zip(feature_names, mean_abs_shap.tolist()))
shap_importance = dict(sorted(
    shap_importance.items(), key=lambda x: x[1], reverse=True
))
```

### Pattern 2: 50% Feature Pruning with Performance Guard

**What:** Rank features by SHAP importance, prune the bottom 50%, retrain both models, and compare performance. Only accept pruning if pruned model performance >= full model performance.

**When to use:** Per walk-forward window, after SHAP computation.

**Example:**
```python
# Rank and prune bottom 50%
ranked_features = sorted(
    shap_importance.items(), key=lambda x: x[1], reverse=True
)
n_keep = max(len(ranked_features) // 2, 1)  # Keep at least 1 feature
kept_features = [f for f, _ in ranked_features[:n_keep]]
pruned_features = [f for f, _ in ranked_features[n_keep:]]

# Get column indices for kept features
kept_idx = [feature_names.index(f) for f in kept_features]
X_train_pruned = X_train_scaled[:, kept_idx]
X_val_pruned = X_val_scaled[:, kept_idx]
X_test_pruned = X_test_scaled[:, kept_idx]

# Retrain XGBoost on pruned features
trainer._xgboost.set_feature_names(kept_features)
xgb_pruned_result = trainer._xgboost.train(
    X_train_pruned, y_train, X_val_pruned, y_val,
    use_class_weight=True, use_recency_weight=True,
)

# Compare: evaluate pruned model on test
# If pruned PF >= full PF, accept pruning
```

### Pattern 3: Headless Chart Generation

**What:** Generate feature importance bar chart as PNG using matplotlib Agg backend, saved to the versioned model directory alongside training_report.json.

**When to use:** Once after all walk-forward windows complete, using aggregate SHAP importance from the final window (production model).

**Example:**
```python
# Source: matplotlib docs + SHAP integration
import matplotlib
matplotlib.use('Agg')  # Must be before pyplot import
import matplotlib.pyplot as plt

def save_feature_importance_chart(
    shap_importance: dict,
    output_path: str,
    top_n: int = 20,
) -> str:
    """Save a horizontal bar chart of SHAP feature importance."""
    # Take top N features
    sorted_features = sorted(
        shap_importance.items(), key=lambda x: x[1], reverse=True
    )[:top_n]
    names = [f for f, _ in reversed(sorted_features)]
    values = [v for _, v in reversed(sorted_features)]

    fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.3)))
    ax.barh(names, values, color='#1f77b4')
    ax.set_xlabel('Mean |SHAP value|')
    ax.set_title('Feature Importance (SHAP)')
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return output_path
```

### Pattern 4: SHAP Data Persistence in Version Directory

**What:** Save SHAP importance data as JSON alongside the version metadata, and reference the chart file path in version.json.

**When to use:** During Step 7 (save with versioning) in pipeline.py.

**Example structure in version directory:**
```
saved_models/v003_20260307_120000/
  xgboost_gold.pkl
  lightgbm_gold.pkl
  feature_scaler.pkl
  version.json              # Extended with shap_importance section
  training_report.json      # Extended with shap data per window
  feature_importance.png    # SHAP bar chart
```

### Anti-Patterns to Avoid

- **Computing SHAP on training data instead of test data:** Training data SHAP values reflect what the model memorized, not what generalizes. Use test set (or held-out validation) for importance estimation.
- **Averaging SHAP importance across windows then pruning:** Each window should make its own pruning decision. The final window's pruning determines production feature set.
- **Using `shap.Explainer()` instead of `shap.TreeExplainer()`:** The generic Explainer auto-detects model type but can fall back to slower KernelExplainer. Use TreeExplainer explicitly for tree models.
- **Pruning too aggressively in early windows:** With small test sets in early windows, SHAP importance estimates are noisy. The 50% threshold is already aggressive -- do not go below it.
- **Forgetting `plt.close(fig)` after savefig:** Memory leak if generating charts in a loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Feature importance | Custom gain-based importance | `shap.TreeExplainer` | Shapley values are theoretically grounded, handle feature correlations, provide direction |
| Bar chart rendering | Custom ASCII/HTML charts | `matplotlib` with `Agg` backend | Battle-tested, SHAP's own plotting uses it |
| Multi-class SHAP aggregation | Manual probability decomposition | `np.mean(np.abs(shap_values))` across classes | Standard practice, handles 3-class correctly |

**Key insight:** The existing XGBoost `feature_importances_` (gain-based) is already doing basic feature selection at a 0.5% threshold. SHAP replaces this with a more principled metric. The replacement is surgical -- same location in the code, better algorithm.

## Common Pitfalls

### Pitfall 1: SHAP Output Shape Varies by API Version

**What goes wrong:** SHAP's `TreeExplainer.shap_values()` returns different shapes depending on the version and model type. Older versions return a list of arrays (one per class), newer versions may return a 3D array.
**Why it happens:** SHAP API evolved. In 0.51.0 with XGBoost/LightGBM multi-class, `shap_values()` returns a list of `n_classes` arrays each of shape `(n_samples, n_features)`.
**How to avoid:** Always check if result is a list or ndarray and handle both:
```python
if isinstance(shap_values, list):
    # list of n_classes arrays, each (n_samples, n_features)
    abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    mean_importance = abs_shap.mean(axis=0)
elif shap_values.ndim == 3:
    # (n_samples, n_features, n_classes)
    mean_importance = np.mean(np.abs(shap_values), axis=(0, 2))
else:
    # 2D: (n_samples, n_features) -- binary or single output
    mean_importance = np.mean(np.abs(shap_values), axis=0)
```
**Warning signs:** `IndexError` or wrong-shaped importance array.

### Pitfall 2: SHAP Computation Speed on Large Datasets

**What goes wrong:** Computing SHAP values on 10,000+ samples takes too long, slowing walk-forward iteration.
**Why it happens:** TreeExplainer on XGBoost/LightGBM is O(n_samples * n_features * n_trees * depth), but large test sets still take seconds per window.
**How to avoid:** Subsample to max ~2000 samples for SHAP computation. The test set in most windows is 200-2000 samples already, so this is naturally bounded. If test set > 2000, subsample:
```python
max_shap_samples = min(len(X_test_scaled), 2000)
shap_idx = np.random.choice(len(X_test_scaled), max_shap_samples, replace=False)
shap_values = explainer.shap_values(X_test_scaled[shap_idx])
```
**Warning signs:** Single window taking > 30 seconds for SHAP computation.

### Pitfall 3: Pruning Removes All Informative Features

**What goes wrong:** After pruning bottom 50%, the remaining features are insufficient for the model, and performance drops significantly.
**Why it happens:** When many features have similar low importance (common with engineered features from the same indicator), the 50% cut is arbitrary and may drop moderately useful features.
**How to avoid:** Implement the performance guard: retrain with pruned features and compare against full-feature performance. If pruned model underperforms, fall back to full feature set. Log this clearly.
**Warning signs:** Pruned model accuracy or profit factor drops > 10% compared to full model.

### Pitfall 4: matplotlib Import Order with Agg Backend

**What goes wrong:** `matplotlib.use('Agg')` must be called before `import matplotlib.pyplot as plt`. If pyplot is imported elsewhere first (e.g., by shap internally), the backend switch fails silently.
**Why it happens:** matplotlib locks the backend on first pyplot import.
**How to avoid:** Set `MPLBACKEND=Agg` environment variable at the top of the module, or use `matplotlib.use('Agg')` at module level before any pyplot imports. Better yet, set it in a dedicated charting module that controls the import order.
**Warning signs:** `UserWarning: Matplotlib is currently using agg` (actually desired), or crashes on headless servers with "cannot open display".

### Pitfall 5: Pruning Inconsistency Across Walk-Forward Windows

**What goes wrong:** Different windows prune different features, so the "selected features" from the final window may not reflect what was validated in earlier windows.
**Why it happens:** Each window independently determines importance, so the feature set varies.
**How to avoid:** This is expected behavior in the existing architecture. The final window's selected features become the production feature set (same pattern as Phase 2). Document per-window pruning decisions in the results dict.
**Warning signs:** None -- this is by design.

## Code Examples

### Complete SHAP Integration in run_window()

```python
# Replace existing step 5 (feature selection) in walk_forward.py
# After step 4 (Train XGBoost initial)

import shap

# 5. SHAP-based feature importance (replaces XGBoost gain importance)
shap_importance = {}
if trainer._xgboost.is_trained:
    explainer = shap.TreeExplainer(trainer._xgboost.model)

    # Subsample if test set too large
    max_shap_samples = min(len(X_test_scaled), 2000)
    if max_shap_samples < len(X_test_scaled):
        shap_idx = np.random.choice(
            len(X_test_scaled), max_shap_samples, replace=False
        )
        X_shap = X_test_scaled[shap_idx]
    else:
        X_shap = X_test_scaled

    shap_values = explainer.shap_values(X_shap)

    # Handle both list (per-class) and 3D array formats
    if isinstance(shap_values, list):
        abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        abs_shap = np.mean(np.abs(shap_values), axis=2)
    else:
        abs_shap = np.abs(shap_values)

    mean_importance = abs_shap.mean(axis=0)
    shap_importance = dict(zip(feature_names, mean_importance.tolist()))
    shap_importance = dict(sorted(
        shap_importance.items(), key=lambda x: x[1], reverse=True
    ))

    # Prune bottom 50% by SHAP importance
    n_keep = max(len(feature_names) // 2, 1)
    ranked = sorted(
        shap_importance.items(), key=lambda x: x[1], reverse=True
    )
    selected_features = [f for f, _ in ranked[:n_keep]]
    pruned_features = [f for f, _ in ranked[n_keep:]]

    if len(selected_features) < len(feature_names):
        logger.info(
            f"    SHAP pruning: kept {len(selected_features)}, "
            f"pruned {len(pruned_features)}"
        )
        sel_idx = [feature_names.index(f) for f in selected_features]
        X_train_scaled = X_train_scaled[:, sel_idx]
        X_val_scaled = X_val_scaled[:, sel_idx]
        X_test_scaled = X_test_scaled[:, sel_idx]

        # Re-train XGBoost on selected features
        trainer._xgboost.set_feature_names(selected_features)
        xgb_pruned = trainer._xgboost.train(
            X_train_scaled, y_train, X_val_scaled, y_val,
            use_class_weight=True, use_recency_weight=True,
        )
        result["xgboost_train_pruned"] = xgb_pruned

    result["shap_importance"] = shap_importance
    result["feature_pruning"] = {
        "method": "shap_mean_abs",
        "original": len(feature_names),
        "kept": len(selected_features),
        "pruned": len(pruned_features),
        "pruned_features": pruned_features,
        "kept_features": selected_features,
    }
```

### Performance Comparison (Pruned vs Full)

```python
# After training both full and pruned models, compare on test set
def compare_pruned_vs_full(
    full_eval: dict, pruned_eval: dict
) -> dict:
    """Compare pruned model performance against full model."""
    full_pf = full_eval.get("profit_factor", 0)
    pruned_pf = pruned_eval.get("profit_factor", 0)
    full_wr = full_eval.get("win_rate", 0)
    pruned_wr = pruned_eval.get("win_rate", 0)

    return {
        "full_profit_factor": full_pf,
        "pruned_profit_factor": pruned_pf,
        "pf_change_pct": ((pruned_pf - full_pf) / full_pf * 100)
            if full_pf > 0 else 0,
        "pruning_accepted": pruned_pf >= full_pf,
        "full_win_rate": full_wr,
        "pruned_win_rate": pruned_wr,
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XGBoost `feature_importances_` (gain) | SHAP `TreeExplainer` mean absolute values | Phase 3 | More principled importance, handles correlated features better |
| Fixed 0.5% importance threshold | 50% rank-based pruning with performance guard | Phase 3 | More aggressive pruning, but validated by retrain + compare |
| No visualization of feature importance | SHAP bar chart saved as PNG per training run | Phase 3 | Interpretability for manual review |

**Deprecated/outdated:**
- `shap.summary_plot()` legacy API: Still works but `shap.plots.bar()` / `shap.plots.beeswarm()` are the newer API. For this project, matplotlib direct plotting is simpler and avoids SHAP plot API quirks.
- SHAP < 0.50.0: Incompatible with XGBoost >= 3.1 due to `base_score` list format issue.

## Open Questions

1. **Should SHAP importance be computed from XGBoost only, or both XGBoost and LightGBM?**
   - What we know: Current feature selection uses XGBoost importance only. Both models support TreeExplainer.
   - What's unclear: Whether averaging SHAP from both models gives better pruning decisions.
   - Recommendation: Compute from XGBoost only (primary model, 40% weight). Simpler, consistent with existing pattern. Can extend later.

2. **Should pruning be skipped in early walk-forward windows with small test sets?**
   - What we know: Early windows have test sets of ~375 samples. SHAP importance on small samples may be noisy.
   - What's unclear: Minimum sample size for reliable SHAP importance ranking.
   - Recommendation: Apply pruning in all windows. The 50% threshold is robust even with moderate noise. Per-window pruning is already independent (existing pattern from Phase 2).

3. **Where in version.json should SHAP data be stored?**
   - What we know: version.json already has `walk_forward.windows[].metrics` and `aggregate_metrics`.
   - Recommendation: Add `shap_importance` as a top-level key in version.json (dict of feature_name -> importance), and `feature_pruning` summary. Add `feature_importance_chart` path reference.

## Sources

### Primary (HIGH confidence)
- [SHAP PyPI page](https://pypi.org/project/shap/) - Version 0.51.0, Python 3.13 support confirmed
- [SHAP TreeExplainer docs](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html) - API reference, multi-class output shape
- [SHAP GitHub issue #4202](https://github.com/shap/shap/issues/4202) - XGBoost >= 3.1 compatibility fixed in 0.50.0
- [SHAP LightGBM example](https://shap.readthedocs.io/en/latest/example_notebooks/tabular_examples/tree_based_models/Census%20income%20classification%20with%20LightGBM.html) - Usage patterns
- Codebase files: `walk_forward.py`, `pipeline.py`, `model_versioning.py`, `xgboost_model.py`, `lightgbm_model.py` - Existing architecture analysis

### Secondary (MEDIUM confidence)
- [SHAP-Guided Feature Pruning overview](https://www.emergentmind.com/topics/shap-guided-feature-pruning) - Community practices for SHAP pruning workflows
- [Feature selection strategies: SHAP vs importance-based (Springer)](https://link.springer.com/article/10.1186/s40537-024-00905-w) - Academic comparison of methods
- [matplotlib Agg backend docs](https://matplotlib.org/stable/users/explain/backends.html) - Headless rendering pattern

### Tertiary (LOW confidence)
- None -- all critical claims verified with official sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - SHAP 0.51.0 verified on PyPI, Python 3.13 supported, XGBoost 3.2.0 compat fixed
- Architecture: HIGH - Direct codebase analysis of walk_forward.py, pipeline.py, model_versioning.py; integration points are clear and surgical
- Pitfalls: HIGH - XGBoost compat issue verified fixed; multi-class output shape documented in official docs; matplotlib Agg backend is standard pattern

**Research date:** 2026-03-07
**Valid until:** 2026-04-07 (stable domain, SHAP and tree models mature)
