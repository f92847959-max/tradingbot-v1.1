"""
LightGBM Model -- Fast gradient boosting for gold trading.

LightGBM is the secondary model (35% weight in ensemble).
Faster than XGBoost, similar accuracy.
"""

import logging
import os
from typing import Any, Dict, Optional

import joblib
import numpy as np

from .base_model import BaseModel

logger = logging.getLogger(__name__)


class LightGBMModel(BaseModel):
    """
    LightGBM model for BUY/SELL/HOLD classification.

    Uses histogram-based gradient boosting for fast training.
    """

    DEFAULT_PARAMS: Dict[str, Any] = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_samples": 20,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "is_unbalance": True,  # Automatic class balancing
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the LightGBM model.

        Args:
            params: Optional custom hyperparameters
        """
        super().__init__(name="lightgbm")
        self._params = {**self.DEFAULT_PARAMS}
        if params:
            self._params.update(params)
        self._best_iteration: int = 0

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
        early_stopping_rounds: int = 50,
        use_recency_weight: bool = True,
    ) -> Dict[str, Any]:
        """
        Train the LightGBM model.

        Args:
            X_train: Training features
            y_train: Training labels (-1=SELL, 0=HOLD, 1=BUY)
            X_val: Validation features
            y_val: Validation labels
            early_stopping_rounds: Early stopping rounds
            use_recency_weight: Weight more recent data higher

        Returns:
            Dict with training info
        """
        import lightgbm as lgb

        logger.info(f"LightGBM training starting: {X_train.shape[0]} samples, "
                     f"{X_train.shape[1]} features")

        y_train_mapped = self._map_labels(y_train)

        # Recency weights (more recent data is more important)
        sample_weights = None
        if use_recency_weight:
            sample_weights = np.linspace(0.5, 1.5, len(X_train))
            sample_weights /= sample_weights.mean()

        # Create model (is_unbalance=True in DEFAULT_PARAMS)
        params = {k: v for k, v in self._params.items()
                  if k not in ("early_stopping_rounds",)}
        self.model = lgb.LGBMClassifier(**params)

        # Training
        fit_params: Dict[str, Any] = {}
        if sample_weights is not None:
            fit_params["sample_weight"] = sample_weights
        if X_val is not None and y_val is not None:
            y_val_mapped = self._map_labels(y_val)
            fit_params["eval_set"] = [(X_val, y_val_mapped)]
            fit_params["callbacks"] = [
                lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=False),
                lgb.log_evaluation(period=0),
            ]

        self.model.fit(X_train, y_train_mapped, **fit_params)
        self._is_trained = True

        self._best_iteration = getattr(self.model, "best_iteration_", self._params["n_estimators"])

        logger.info(f"LightGBM trained! Best iteration: {self._best_iteration}")

        return {
            "model": self.name,
            "best_iteration": self._best_iteration,
            "n_samples": X_train.shape[0],
            "n_features": X_train.shape[1],
        }

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Return probabilities per class.

        Args:
            X: Feature matrix [n_samples, n_features]

        Returns:
            Probabilities [n_samples, 3] for [SELL, HOLD, BUY]
        """
        if not self._is_trained:
            raise RuntimeError("LightGBM is not trained!")

        if X.ndim == 1:
            X = X.reshape(1, -1)

        probs = self.model.predict_proba(X)
        return probs

    def save(self, path: str) -> None:
        """Save the LightGBM model as a .pkl file."""
        if not self._is_trained:
            raise RuntimeError("Model not trained!")

        self._ensure_dir(path)
        data = {
            "model": self.model,
            "params": self._params,
            "feature_names": self._feature_names,
            "best_iteration": self._best_iteration,
        }
        joblib.dump(data, path)
        logger.info(f"LightGBM saved: {path}")

    def load(self, path: str) -> None:
        """Load a saved LightGBM model."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        data = joblib.load(path)
        self.model = data["model"]
        self._params = data["params"]
        self._feature_names = data.get("feature_names", [])
        self._best_iteration = data.get("best_iteration", 0)
        self._is_trained = True
        logger.info(f"LightGBM loaded: {path}")

    def get_feature_importance(self) -> Dict[str, float]:
        """Return the feature importance."""
        if not self._is_trained:
            return {}

        importances = self.model.feature_importances_
        names = self._feature_names if self._feature_names else \
            [f"feature_{i}" for i in range(len(importances))]

        importance_dict = dict(zip(names, importances.tolist()))
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))

    @staticmethod
    def _map_labels(y: np.ndarray) -> np.ndarray:
        """Map labels from [-1, 0, 1] to [0, 1, 2]."""
        return (np.array(y) + 1).astype(int)

    @staticmethod
    def _unmap_labels(y: np.ndarray) -> np.ndarray:
        """Map labels from [0, 1, 2] back to [-1, 0, 1]."""
        return (np.array(y) - 1).astype(int)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from sklearn.datasets import make_classification

    X, y = make_classification(
        n_samples=1000, n_features=20, n_informative=10,
        n_classes=3, random_state=42
    )
    y = y - 1

    split = int(0.8 * len(X))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    model = LightGBMModel({"n_estimators": 50})
    result = model.train(X_train, y_train, X_val, y_val)
    print(f"Training: {result}")

    pred = model.predict_single(X_val[0])
    print(f"Prediction: {pred}")

    top5 = list(model.get_feature_importance().items())[:5]
    print(f"Top-5 features: {top5}")

    print("LightGBM test successful!")
