"""Tests for ai_engine.training.shap_importance module."""

import os

import numpy as np
import pytest
from xgboost import XGBClassifier

from ai_engine.training.shap_importance import (
    compute_shap_importance,
    save_feature_importance_chart,
)


def _train_xgb_classifier(n_features=20, n_samples=500, n_classes=3, seed=42):
    """Train a small XGBClassifier on synthetic multi-class data."""
    rng = np.random.RandomState(seed)
    X = rng.randn(n_samples, n_features)
    y = rng.randint(0, n_classes, n_samples)
    feature_names = [f"feature_{i}" for i in range(n_features)]

    model = XGBClassifier(
        n_estimators=10,
        max_depth=3,
        use_label_encoder=False,
        eval_metric="mlogloss",
        verbosity=0,
        random_state=seed,
    )
    model.fit(X, y)

    return model, X, feature_names


class TestComputeShapImportance:
    """Tests for compute_shap_importance function."""

    def test_returns_sorted_dict(self):
        """Train a small XGBClassifier on synthetic 3-class data,
        verify return is a dict with all feature names as keys,
        values are non-negative floats, sorted descending."""
        model, X, feature_names = _train_xgb_classifier(
            n_features=20, n_samples=500, n_classes=3
        )

        result = compute_shap_importance(model, X, feature_names)

        # Check type
        assert isinstance(result, dict)

        # Check all feature names present
        assert set(result.keys()) == set(feature_names)
        assert len(result) == 20

        # Check values are non-negative floats
        for name, value in result.items():
            assert isinstance(value, float), f"{name} value is not float"
            assert value >= 0, f"{name} has negative importance: {value}"

        # Check sorted descending
        values = list(result.values())
        assert values == sorted(values, reverse=True), "Not sorted descending"

    def test_subsamples_large_data(self):
        """Pass X_data with 5000 rows and max_samples=100.
        Verify function completes and returns correct number of features."""
        model, _, feature_names = _train_xgb_classifier(
            n_features=20, n_samples=500, n_classes=3
        )

        # Create larger dataset
        rng = np.random.RandomState(99)
        X_large = rng.randn(5000, 20)

        result = compute_shap_importance(
            model, X_large, feature_names, max_samples=100
        )

        assert isinstance(result, dict)
        assert len(result) == 20

        # Values should still be non-negative
        for value in result.values():
            assert value >= 0

    def test_handles_list_format(self):
        """Verify function works with XGBoost multi-class output
        (which returns list of arrays for shap_values)."""
        model, X, feature_names = _train_xgb_classifier(
            n_features=10, n_samples=200, n_classes=3
        )

        result = compute_shap_importance(model, X, feature_names)

        assert isinstance(result, dict)
        assert len(result) == 10

        # All values should be valid
        for value in result.values():
            assert isinstance(value, float)
            assert np.isfinite(value)
            assert value >= 0


class TestSaveFeatureImportanceChart:
    """Tests for save_feature_importance_chart function."""

    def test_creates_png(self, tmp_path):
        """Create a mock importance dict, save chart,
        verify PNG file exists with non-zero size."""
        importance = {
            f"feature_{i}": float(20 - i) for i in range(20)
        }
        output_path = str(tmp_path / "chart.png")

        result = save_feature_importance_chart(importance, output_path)

        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

    def test_creates_parent_dirs(self, tmp_path):
        """Call with a path whose parent doesn't exist yet,
        verify it creates the directory and the file."""
        importance = {"feat_a": 0.5, "feat_b": 0.3, "feat_c": 0.1}
        nested_path = str(tmp_path / "subdir1" / "subdir2" / "chart.png")

        # Parent dirs do not exist
        assert not os.path.exists(os.path.dirname(nested_path))

        result = save_feature_importance_chart(importance, nested_path)

        assert result == nested_path
        assert os.path.exists(nested_path)
        assert os.path.getsize(nested_path) > 0

    def test_top_n(self, tmp_path):
        """Pass 30 features but top_n=10, verify chart is created
        (ensure function accepts the parameter without crashing)."""
        importance = {
            f"feature_{i}": float(30 - i) * 0.1 for i in range(30)
        }
        output_path = str(tmp_path / "chart_top10.png")

        result = save_feature_importance_chart(
            importance, output_path, top_n=10
        )

        assert result == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0
