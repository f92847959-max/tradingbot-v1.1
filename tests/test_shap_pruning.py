"""Tests for SHAP-based feature pruning in walk-forward windows."""

import numpy as np

from ai_engine.training.walk_forward import WalkForwardValidator, WindowSpec


def _make_trainer(tp_pips=50.0, sl_pips=30.0, spread_pips=2.5):
    """Create a minimal ModelTrainer with real XGBoost/LightGBM models."""
    from ai_engine.models.xgboost_model import XGBoostModel
    from ai_engine.models.lightgbm_model import LightGBMModel
    from ai_engine.training.evaluation import ModelEvaluator

    class MinimalTrainer:
        def __init__(self):
            self._xgboost = XGBoostModel({"n_estimators": 20, "max_depth": 3})
            self._lightgbm = LightGBMModel({"n_estimators": 20, "max_depth": 3})
            self._evaluator = ModelEvaluator()
            self.tp_pips = tp_pips
            self.sl_pips = sl_pips
            self.spread_pips = spread_pips

    return MinimalTrainer()


def _make_synthetic_data(n_features=20, n_samples=2000, seed=42):
    """Create synthetic data suitable for a single walk-forward window.

    Returns X (n_samples, n_features), y (n_samples,), feature_names.
    Labels are in signal space: -1 (SELL), 0 (HOLD), 1 (BUY).
    """
    rng = np.random.RandomState(seed)
    X = rng.randn(n_samples, n_features).astype(np.float32)
    y = rng.choice([-1, 0, 1], size=n_samples)
    feature_names = [f"feat_{i}" for i in range(n_features)]
    return X, y, feature_names


def _run_single_window(n_features=20, n_samples=2000, seed=42):
    """Run a single walk-forward window and return the result dict."""
    X, y, feature_names = _make_synthetic_data(n_features, n_samples, seed)
    trainer = _make_trainer()
    validator = WalkForwardValidator(
        purge_gap=10,
        min_train_samples=500,
        min_test_samples=200,
    )

    # Create a window that fits within our data
    window = WindowSpec(
        window_id=0,
        train_start=0,
        train_end=1500,
        test_start=1510,
        test_end=2000,
    )

    result = validator.run_window(window, X, y, feature_names, trainer)
    return result, feature_names


class TestShapImportanceInWindowResult:
    """Test that SHAP importance is computed and stored in window result."""

    def test_shap_importance_in_window_result(self):
        """Run a single walk-forward window, verify result['shap_importance']
        is a non-empty dict with feature names as keys."""
        result, feature_names = _run_single_window()

        assert "shap_importance" in result, "result missing 'shap_importance' key"
        shap_imp = result["shap_importance"]
        assert isinstance(shap_imp, dict), "shap_importance should be a dict"
        assert len(shap_imp) > 0, "shap_importance should not be empty"

        # All keys should be valid feature names
        for key in shap_imp:
            assert key in feature_names, f"Unknown feature name: {key}"

        # All values should be non-negative floats
        for name, value in shap_imp.items():
            assert isinstance(value, float), f"{name} value is not float"
            assert value >= 0, f"{name} has negative importance: {value}"


class TestFeaturePruningInWindowResult:
    """Test that feature pruning result is structured correctly."""

    def test_feature_pruning_in_window_result(self):
        """Verify result['feature_pruning'] exists with expected keys and
        method == 'shap_mean_abs'."""
        result, _ = _run_single_window()

        assert "feature_pruning" in result, "result missing 'feature_pruning' key"
        pruning = result["feature_pruning"]

        expected_keys = {
            "method",
            "original_count",
            "kept_count",
            "pruned_count",
            "kept_features",
            "pruned_features",
            "pruning_accepted",
        }
        assert expected_keys.issubset(
            set(pruning.keys())
        ), f"Missing keys: {expected_keys - set(pruning.keys())}"

        assert pruning["method"] == "shap_mean_abs"
        assert isinstance(pruning["kept_features"], list)
        assert isinstance(pruning["pruned_features"], list)
        assert isinstance(pruning["pruning_accepted"], bool)


class TestPruningKeepsAtLeastOneFeature:
    """Test that pruning always keeps at least 1 feature."""

    def test_pruning_keeps_at_least_one_feature(self):
        """Verify kept_count >= 1 even with very few features."""
        # Use 3 features -- pruning should keep at least 1
        result, _ = _run_single_window(n_features=3, n_samples=2000, seed=99)
        pruning = result["feature_pruning"]
        assert pruning["kept_count"] >= 1, (
            f"Expected at least 1 kept feature, got {pruning['kept_count']}"
        )

    def test_pruning_keeps_at_least_one_with_two_features(self):
        """With 2 features, should keep exactly 1."""
        result, _ = _run_single_window(n_features=2, n_samples=2000, seed=77)
        pruning = result["feature_pruning"]
        assert pruning["kept_count"] >= 1


class TestPruningRemovesApproximately50Percent:
    """Test that pruning removes approximately 50% of features."""

    def test_pruning_removes_approximately_50_percent(self):
        """Verify kept_count is approximately original_count // 2."""
        result, _ = _run_single_window(n_features=20)
        pruning = result["feature_pruning"]

        # If pruning was accepted, check the ratio
        if pruning["pruning_accepted"]:
            original = pruning["original_count"]
            kept = pruning["kept_count"]
            expected_kept = max(original // 2, 1)
            # Allow +/- 1 tolerance for rounding
            assert abs(kept - expected_kept) <= 1, (
                f"Expected ~{expected_kept} kept features, got {kept}"
            )
            assert pruning["pruned_count"] == original - kept
        else:
            # If pruning was rejected, kept_count should equal original
            assert pruning["kept_count"] == pruning["original_count"]


class TestSelectedFeaturesUpdatedAfterPruning:
    """Test that selected_features reflects pruning result."""

    def test_selected_features_updated_after_pruning(self):
        """Verify result['selected_features'] has length equal to
        pruning_result['kept_count'] when pruning is accepted."""
        result, feature_names = _run_single_window(n_features=20)
        pruning = result["feature_pruning"]

        assert "selected_features" in result, "result missing 'selected_features'"
        selected = result["selected_features"]

        if pruning["pruning_accepted"]:
            assert len(selected) == pruning["kept_count"], (
                f"selected_features length ({len(selected)}) != "
                f"kept_count ({pruning['kept_count']})"
            )
            # Verify all selected features are in kept_features
            assert set(selected) == set(pruning["kept_features"])
        else:
            # If pruning was rejected, all features should be selected
            assert len(selected) == len(feature_names)
