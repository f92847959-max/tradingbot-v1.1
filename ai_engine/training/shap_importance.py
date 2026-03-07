"""SHAP-based feature importance analysis for tree models.

Provides functions to compute SHAP feature importance from trained
XGBoost/LightGBM models and generate feature importance bar charts.
"""

import os

import matplotlib
matplotlib.use('Agg')  # Must be before pyplot import for headless rendering
import matplotlib.pyplot as plt

import numpy as np
import shap


def compute_shap_importance(
    model,
    X_data: np.ndarray,
    feature_names: list[str],
    max_samples: int = 2000,
) -> dict[str, float]:
    """Compute mean absolute SHAP importance for each feature.

    Uses shap.TreeExplainer for exact Shapley values on tree models
    (XGBoost, LightGBM). Handles multi-class output (3 classes:
    SELL/HOLD/BUY) by averaging |SHAP| across samples and classes.

    Args:
        model: Trained XGBClassifier or LGBMClassifier instance
            (the .model attribute from XGBoostModel/LightGBMModel).
        X_data: Feature matrix to explain, shape (n_samples, n_features).
            Should be test/validation data, NOT training data.
        feature_names: List of feature names matching X_data columns.
        max_samples: Maximum samples for SHAP computation. If X_data
            has more rows, a random subsample is used.

    Returns:
        Dict of {feature_name: mean_abs_shap_value}, sorted descending
        by importance.
    """
    explainer = shap.TreeExplainer(model)

    # Subsample if data exceeds max_samples
    if len(X_data) > max_samples:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_data), max_samples, replace=False)
        X_shap = X_data[idx]
    else:
        X_shap = X_data

    shap_values = explainer.shap_values(X_shap)

    # Handle output format variations across SHAP versions:
    # - list of n_classes arrays, each (n_samples, n_features)
    # - 3D array (n_samples, n_features, n_classes)
    # - 2D array (n_samples, n_features) for binary/single output
    if isinstance(shap_values, list):
        # Per-class list: average absolute values across classes then samples
        abs_shap = np.mean([np.abs(sv) for sv in shap_values], axis=0)
        mean_importance = abs_shap.mean(axis=0)
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        # 3D array: mean absolute across samples (axis=0) and classes (axis=2)
        mean_importance = np.mean(np.abs(shap_values), axis=(0, 2))
    else:
        # 2D array: mean absolute across samples
        mean_importance = np.mean(np.abs(shap_values), axis=0)

    # Build sorted dict (descending by importance)
    importance_dict = dict(zip(feature_names, mean_importance.tolist()))
    importance_dict = dict(
        sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
    )

    return importance_dict


def save_feature_importance_chart(
    shap_importance: dict[str, float],
    output_path: str,
    top_n: int = 20,
) -> str:
    """Save a horizontal bar chart of SHAP feature importance as PNG.

    Args:
        shap_importance: Dict of {feature_name: importance} (from
            compute_shap_importance).
        output_path: File path for the PNG output.
        top_n: Maximum number of features to display (top N by importance).

    Returns:
        The output_path string (for chaining/logging).
    """
    # Sort descending and take top N
    sorted_features = sorted(
        shap_importance.items(), key=lambda x: x[1], reverse=True
    )[:top_n]

    # Reverse for horizontal bar chart (most important at bottom = SHAP convention)
    names = [f for f, _ in reversed(sorted_features)]
    values = [v for _, v in reversed(sorted_features)]

    fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.3)))
    ax.barh(names, values, color='#1f77b4')
    ax.set_xlabel('Mean |SHAP value|')
    ax.set_title('Feature Importance (SHAP)')

    # Create parent directory if needed
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    return output_path
