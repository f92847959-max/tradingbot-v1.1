"""
XGBoost Model -- Gradient boosting for gold trading.

XGBoost is the primary model (40% weight in ensemble).
Particularly good for tabular data with feature engineering.
"""

import logging
import os
from typing import Any, Dict, Optional

import joblib
import numpy as np

from .base_model import BaseModel

logger = logging.getLogger(__name__)


class XGBoostModel(BaseModel):
    """
    XGBoost model for BUY/SELL/HOLD classification.

    Hyperparameters are optimized for gold trading on 5min charts.
    Uses early stopping on a validation set.
    """

    # Default hyperparameters (from README)
    DEFAULT_PARAMS: Dict[str, Any] = {
        "n_estimators": 500,
        "max_depth": 6,
        "learning_rate": 0.05,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 5,
        "gamma": 0.1,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "objective": "multi:softprob",
        "num_class": 3,
        "eval_metric": "mlogloss",
        "random_state": 42,
        "n_jobs": -1,
        "verbosity": 0,
    }

    def __init__(self, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the XGBoost model.

        Args:
            params: Optional custom hyperparameters (override defaults)
        """
        super().__init__(name="xgboost")
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
        use_class_weight: bool = True,
        use_recency_weight: bool = True,
    ) -> Dict[str, Any]:
        """
        Train the XGBoost model.

        Args:
            X_train: Training features
            y_train: Training labels (0=SELL, 1=HOLD, 2=BUY)
            X_val: Validation features (for early stopping)
            y_val: Validation labels
            early_stopping_rounds: Stop after N rounds without improvement
            use_class_weight: Use class weighting (balanced)
            use_recency_weight: Weight more recent data higher

        Returns:
            Dict with training info
        """
        import xgboost as xgb

        logger.info(f"XGBoost training starting: {X_train.shape[0]} samples, "
                     f"{X_train.shape[1]} features")

        # Labels must start at 0: SELL=-1->0, HOLD=0->1, BUY=1->2
        y_train_mapped = self._map_labels(y_train)

        # Compute sample weights
        sample_weights = self._compute_sample_weights(
            y_train_mapped, len(X_train),
            use_class_weight=use_class_weight,
            use_recency_weight=use_recency_weight,
        )

        # Create model
        params = {k: v for k, v in self._params.items()
                  if k not in ("early_stopping_rounds",)}
        self.model = xgb.XGBClassifier(**params)

        # Training with or without early stopping
        fit_params: Dict[str, Any] = {"sample_weight": sample_weights}
        if X_val is not None and y_val is not None:
            y_val_mapped = self._map_labels(y_val)
            fit_params["eval_set"] = [(X_val, y_val_mapped)]
            fit_params["verbose"] = False
            # XGBoost >= 2.0 uses callbacks for early stopping
            try:
                from xgboost.callback import EarlyStopping
                self.model.set_params(
                    callbacks=[EarlyStopping(rounds=early_stopping_rounds,
                                            metric_name="mlogloss",
                                            save_best=True)]
                )
            except ImportError:
                # Fallback for older versions
                self.model.set_params(early_stopping_rounds=early_stopping_rounds)

        self.model.fit(X_train, y_train_mapped, **fit_params)
        self._is_trained = True

        # Best iteration
        self._best_iteration = getattr(self.model, "best_iteration", self._params["n_estimators"])

        logger.info(f"XGBoost trained! Best iteration: {self._best_iteration}")

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
            raise RuntimeError("XGBoost is not trained!")

        if X.ndim == 1:
            X = X.reshape(1, -1)

        probs = self.model.predict_proba(X)
        return probs

    def save(self, path: str) -> None:
        """
        Save the XGBoost model as a .pkl file.

        Args:
            path: File path for the .pkl file
        """
        if not self._is_trained:
            raise RuntimeError("Model not trained -- nothing to save!")

        self._ensure_dir(path)
        data = {
            "model": self.model,
            "params": self._params,
            "feature_names": self._feature_names,
            "best_iteration": self._best_iteration,
        }
        joblib.dump(data, path)
        logger.info(f"XGBoost saved: {path}")

    def load(self, path: str) -> None:
        """
        Load a saved XGBoost model.

        Args:
            path: File path of the .pkl file
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Model file not found: {path}")

        data = joblib.load(path)
        self.model = data["model"]
        self._params = data["params"]
        self._feature_names = data.get("feature_names", [])
        self._best_iteration = data.get("best_iteration", 0)
        self._is_trained = True
        logger.info(f"XGBoost loaded: {path}")

    def get_feature_importance(self) -> Dict[str, float]:
        """
        Return the feature importance.

        Returns:
            Dict with feature name -> importance score
        """
        if not self._is_trained:
            return {}

        importances = self.model.feature_importances_
        names = self._feature_names if self._feature_names else \
            [f"feature_{i}" for i in range(len(importances))]

        importance_dict = dict(zip(names, importances.tolist()))
        # Sorted by importance (highest first)
        return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))

    @staticmethod
    def _compute_sample_weights(
        y: np.ndarray,
        n_samples: int,
        use_class_weight: bool = True,
        use_recency_weight: bool = True,
    ) -> np.ndarray:
        """
        Compute sample weights (class balance + recency).

        Args:
            y: Labels [0, 1, 2]
            n_samples: Number of samples
            use_class_weight: Balance classes
            use_recency_weight: Weight more recent data higher

        Returns:
            Weights per sample
        """
        weights = np.ones(n_samples, dtype=np.float64)

        # Class weighting: inverse frequency
        if use_class_weight:
            classes, counts = np.unique(y, return_counts=True)
            total = len(y)
            for cls, cnt in zip(classes, counts):
                class_weight = total / (len(classes) * cnt)
                weights[y == cls] *= class_weight

        # Recency weighting: exponentially increasing
        if use_recency_weight:
            # Last 20% of data gets up to 2x weight
            recency = np.linspace(0.5, 1.5, n_samples)
            weights *= recency

        # Normalize (average = 1.0)
        weights /= weights.mean()
        return weights

    @staticmethod
    def _map_labels(y: np.ndarray) -> np.ndarray:
        """
        Map labels from [-1, 0, 1] to [0, 1, 2].

        Args:
            y: Labels with values -1 (SELL), 0 (HOLD), 1 (BUY)

        Returns:
            Labels with values 0 (SELL), 1 (HOLD), 2 (BUY)
        """
        return (np.array(y) + 1).astype(int)

    @staticmethod
    def _unmap_labels(y: np.ndarray) -> np.ndarray:
        """Map labels from [0, 1, 2] back to [-1, 0, 1]."""
        return (np.array(y) - 1).astype(int)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from sklearn.datasets import make_classification

    # Synthetic data
    X, y = make_classification(
        n_samples=1000, n_features=20, n_informative=10,
        n_classes=3, random_state=42
    )
    # Map labels to -1, 0, 1
    y = y - 1

    # Split
    split = int(0.8 * len(X))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    # Train model
    model = XGBoostModel({"n_estimators": 50})
    result = model.train(X_train, y_train, X_val, y_val)
    print(f"Training: {result}")

    # Prediction
    pred = model.predict_single(X_val[0])
    print(f"Prediction: {pred}")

    # Feature importance
    top5 = list(model.get_feature_importance().items())[:5]
    print(f"Top-5 features: {top5}")

    print("XGBoost test successful!")
