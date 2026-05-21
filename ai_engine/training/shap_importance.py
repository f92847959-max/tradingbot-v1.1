"""SHAP-based feature importance analysis for tree models.

Provides functions to compute SHAP feature importance from trained
XGBoost/LightGBM models and generate feature importance bar charts.

Phase 18 (D-12): ``shap`` and ``matplotlib`` are imported lazily inside the
functions that use them. At ~80 MB combined import cost, keeping them out of
the module-level import list means tools that only touch this module's
*signatures* (linters, ``--help`` runs, dispatcher startup) pay nothing.
"""

import os

import numpy as np


def _setup_matplotlib_agg():
    """Configure matplotlib for headless Agg rendering and return pyplot.

    Centralises the Agg backend switch so callers don't risk reordering the
    ``matplotlib.use("Agg")`` vs ``import matplotlib.pyplot`` sequence wrong.
    """
    import matplotlib  # lazy import (Phase 18 — keep dispatcher boot fast)

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt  # noqa: E402 -- Agg must be set first
    return plt


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
    import shap  # lazy import (Phase 18 — keep dispatcher boot fast)

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

    plt = _setup_matplotlib_agg()  # lazy (Phase 18)
    fig, ax = plt.subplots(figsize=(10, max(6, len(names) * 0.3)))
    ax.barh(names, values, color='#1f77b4')
    ax.set_xlabel('Mean |SHAP value|')
    ax.set_title('Feature Importance (SHAP)')

    # Create parent directory if needed
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)

    return output_path


def save_training_diagnostic_charts(
    report: dict,
    label_stats: dict,
    output_dir: str,
) -> list[str]:
    """Write the 8 standard training diagnostic PNGs."""
    os.makedirs(output_dir, exist_ok=True)
    chart_specs = [
        ("01_label_distribution.png", _plot_label_distribution),
        ("02_trade_label_balance.png", _plot_trade_label_balance),
        ("03_profit_factor_by_window.png", _plot_window_metric("profit_factor", "Profit Factor")),
        ("04_win_rate_by_window.png", _plot_window_metric("win_rate", "Win Rate")),
        ("05_expectancy_by_window.png", _plot_window_metric("expectancy", "Expectancy")),
        ("06_trade_count_by_window.png", _plot_window_metric("n_trades", "Trades")),
        ("07_aggregate_model_quality.png", _plot_aggregate_quality),
        ("08_feature_pruning_by_window.png", _plot_feature_pruning),
    ]
    paths: list[str] = []
    for filename, plotter in chart_specs:
        path = os.path.join(output_dir, filename)
        plotter(report, label_stats, path)
        paths.append(path)
    return paths


def _save_or_placeholder(path: str, title: str, draw_fn) -> None:
    plt = _setup_matplotlib_agg()  # lazy (Phase 18)
    fig, ax = plt.subplots(figsize=(10, 6))
    try:
        draw_fn(ax)
    except Exception as exc:  # pragma: no cover - defensive diagnostics only
        ax.text(0.5, 0.5, f"No chart data\n{exc}", ha="center", va="center")
        ax.set_axis_off()
    ax.set_title(title)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_label_distribution(_report: dict, label_stats: dict, path: str) -> None:
    def draw(ax):
        labels = ["SELL", "HOLD", "BUY"]
        values = [
            label_stats.get("sell", 0),
            label_stats.get("hold", 0),
            label_stats.get("buy", 0),
        ]
        ax.bar(labels, values, color=["#d62728", "#7f7f7f", "#2ca02c"])
        ax.set_ylabel("Rows")

    _save_or_placeholder(path, "Label Distribution", draw)


def _plot_trade_label_balance(_report: dict, label_stats: dict, path: str) -> None:
    def draw(ax):
        sell = max(float(label_stats.get("sell", 0)), 0.0)
        buy = max(float(label_stats.get("buy", 0)), 0.0)
        hold = max(float(label_stats.get("hold", 0)), 0.0)
        ax.pie(
            [sell, buy, hold],
            labels=["SELL", "BUY", "HOLD"],
            autopct="%1.1f%%",
            colors=["#d62728", "#2ca02c", "#7f7f7f"],
        )

    _save_or_placeholder(path, "Trade Label Balance", draw)


def _plot_window_metric(metric: str, label: str):
    def plot(report: dict, _label_stats: dict, path: str) -> None:
        def draw(ax):
            windows = report.get("per_window", [])
            x = [w.get("window_id", idx) for idx, w in enumerate(windows)]
            for model_key, color in (("xgboost", "#1f77b4"), ("lightgbm", "#ff7f0e")):
                y = [
                    _finite_or_zero(w.get(model_key, {}).get(metric, 0.0))
                    for w in windows
                ]
                ax.plot(x, y, marker="o", label=model_key.upper(), color=color)
            ax.set_xlabel("Window")
            ax.set_ylabel(label)
            ax.legend()
            ax.grid(True, alpha=0.25)

        _save_or_placeholder(path, f"{label} by Window", draw)

    return plot


def _plot_aggregate_quality(report: dict, _label_stats: dict, path: str) -> None:
    def draw(ax):
        aggregate = report.get("aggregate", {})
        labels = ["XGB PF", "LGB PF", "XGB Sharpe", "LGB Sharpe"]
        values = [
            _finite_or_zero(aggregate.get("xgboost", {}).get("profit_factor", 0.0)),
            _finite_or_zero(aggregate.get("lightgbm", {}).get("profit_factor", 0.0)),
            _finite_or_zero(aggregate.get("xgboost", {}).get("sharpe", 0.0)),
            _finite_or_zero(aggregate.get("lightgbm", {}).get("sharpe", 0.0)),
        ]
        ax.bar(labels, values, color=["#1f77b4", "#ff7f0e", "#aec7e8", "#ffbb78"])
        ax.set_ylabel("Value")

    _save_or_placeholder(path, "Aggregate Model Quality", draw)


def _plot_feature_pruning(report: dict, _label_stats: dict, path: str) -> None:
    def draw(ax):
        windows = report.get("per_window", [])
        x = [w.get("window_id", idx) for idx, w in enumerate(windows)]
        kept = [
            w.get("feature_pruning", {}).get("kept_count", 0)
            for w in windows
        ]
        pruned = [
            w.get("feature_pruning", {}).get("pruned_count", 0)
            for w in windows
        ]
        ax.bar(x, kept, label="kept", color="#2ca02c")
        ax.bar(x, pruned, bottom=kept, label="pruned", color="#d62728")
        ax.set_xlabel("Window")
        ax.set_ylabel("Features")
        ax.legend()

    _save_or_placeholder(path, "Feature Pruning by Window", draw)


def _finite_or_zero(value) -> float:
    try:
        value_f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return value_f if np.isfinite(value_f) else 0.0
