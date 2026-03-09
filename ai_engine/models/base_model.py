"""
Base Model -- Abstract base class for all ML models.

Defines the common interface for XGBoost, LightGBM and LSTM.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class BaseModel(ABC):
    """
    Abstract base class for all ML models.

    Each model (XGBoost, LightGBM, LSTM) inherits from this class
    and implements the abstract methods.
    """

    def __init__(self, name: str) -> None:
        """
        Initialize the BaseModel.

        Args:
            name: Name of the model (e.g. 'xgboost', 'lightgbm', 'lstm')
        """
        self.name: str = name
        self.model: Any = None
        self._is_trained: bool = False
        self._feature_names: List[str] = []
        logger.info(f"Model created: {name}")

    @property
    def is_trained(self) -> bool:
        """Return whether the model has been trained."""
        return self._is_trained

    @abstractmethod
    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: Optional[np.ndarray] = None,
        y_val: Optional[np.ndarray] = None,
    ) -> Dict[str, Any]:
        """
        Train the model.

        Args:
            X_train: Training features [n_samples, n_features]
            y_train: Training labels [n_samples]
            X_val: Validation features (for early stopping)
            y_val: Validation labels

        Returns:
            Dict with training info (e.g. best_iteration, train_score)
        """
        pass

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Return probabilities per class.

        Args:
            X: Feature matrix [n_samples, n_features]

        Returns:
            Probabilities [n_samples, n_classes]
            Classes: [SELL(-1), HOLD(0), BUY(1)] -> Index [0, 1, 2]
        """
        pass

    @abstractmethod
    def save(self, path: str) -> None:
        """
        Save the trained model.

        Args:
            path: File path for saving
        """
        pass

    @abstractmethod
    def load(self, path: str) -> None:
        """
        Load a saved model.

        Args:
            path: File path to load from
        """
        pass

    @abstractmethod
    def get_feature_importance(self) -> Dict[str, float]:
        """
        Return the feature importance.

        Returns:
            Dict with feature name -> importance score
        """
        pass

    def predict_single(self, X: np.ndarray) -> Dict[str, Any]:
        """
        Prediction for a single data point.

        Args:
            X: Feature vector [1, n_features] or [n_features]

        Returns:
            Dict with action, confidence and probabilities
        """
        if X.ndim == 1:
            X = X.reshape(1, -1)

        probs = self.predict(X)[0]  # [sell_prob, hold_prob, buy_prob]

        # Labels: 0=SELL, 1=HOLD, 2=BUY
        action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        action_idx = int(np.argmax(probs))

        return {
            "action": action_map[action_idx],
            "confidence": float(probs[action_idx]),
            "probabilities": {
                "SELL": float(probs[0]),
                "HOLD": float(probs[1]),
                "BUY": float(probs[2]),
            },
        }

    def set_feature_names(self, names: List[str]) -> None:
        """Set the feature names (for feature importance)."""
        self._feature_names = names.copy()

    def get_feature_names(self) -> List[str]:
        """Return the feature names."""
        return self._feature_names.copy()

    def _ensure_dir(self, path: str) -> None:
        """Ensure the directory exists."""
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    def __repr__(self) -> str:
        status = "trained" if self._is_trained else "not trained"
        return f"{self.__class__.__name__}(name='{self.name}', status='{status}')"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # BaseModel cannot be instantiated directly (abstract)
    print("BaseModel defined -- abstract methods:")
    for method in ["train", "predict", "save", "load", "get_feature_importance"]:
        print(f"  - {method}()")
    print("  + predict_single() (concrete)")
