"""
Hyperparameter optimization.

Uses RandomizedSearchCV and optional Optuna integration
to find the best hyperparameters for XGBoost and LightGBM.
"""

import logging
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class HyperparameterOptimizer:
    """
    Hyperparameter optimization for XGBoost and LightGBM.

    Uses RandomizedSearchCV from sklearn for efficient search
    in the hyperparameter space.
    """

    # Search spaces for the models
    XGBOOST_SEARCH_SPACE: Dict[str, Any] = {
        "n_estimators": [100, 200, 300, 500, 700, 1000],
        "max_depth": [3, 4, 5, 6, 7, 8],
        "learning_rate": [0.01, 0.02, 0.05, 0.1, 0.15],
        "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_child_weight": [1, 3, 5, 7, 10],
        "gamma": [0, 0.05, 0.1, 0.2, 0.5],
        "reg_alpha": [0, 0.01, 0.1, 0.5, 1.0],
        "reg_lambda": [0.5, 1.0, 1.5, 2.0, 5.0],
    }

    LIGHTGBM_SEARCH_SPACE: Dict[str, Any] = {
        "n_estimators": [100, 200, 300, 500, 700, 1000],
        "max_depth": [3, 4, 5, 6, 7, 8, -1],
        "learning_rate": [0.01, 0.02, 0.05, 0.1, 0.15],
        "subsample": [0.6, 0.7, 0.8, 0.9, 1.0],
        "colsample_bytree": [0.6, 0.7, 0.8, 0.9, 1.0],
        "min_child_samples": [5, 10, 20, 30, 50],
        "reg_alpha": [0, 0.01, 0.1, 0.5, 1.0],
        "reg_lambda": [0.5, 1.0, 1.5, 2.0, 5.0],
        "num_leaves": [15, 31, 50, 63, 80, 100],
    }

    def __init__(self, n_iterations: int = 50, cv_folds: int = 3) -> None:
        """
        Initializes the optimizer.

        Args:
            n_iterations: Number of random sampling iterations
            cv_folds: Number of cross-validation folds
        """
        self.n_iterations = n_iterations
        self.cv_folds = cv_folds
        logger.info(f"HyperparameterOptimizer: {n_iterations} iterations, {cv_folds}-Fold CV")

    def optimize_xgboost(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        search_space: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Optimizes XGBoost hyperparameters.

        Args:
            X_train: Training features
            y_train: Training labels (0, 1, 2)
            search_space: Optional custom search space

        Returns:
            Dict with best parameters and score
        """
        import xgboost as xgb
        from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

        logger.info("Starting XGBoost hyperparameter search...")

        space = search_space or self.XGBOOST_SEARCH_SPACE
        base_model = xgb.XGBClassifier(
            objective="multi:softprob",
            num_class=3,
            eval_metric="mlogloss",
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )

        # TimeSeriesSplit for chronological data
        tscv = TimeSeriesSplit(n_splits=self.cv_folds)

        search = RandomizedSearchCV(
            base_model,
            space,
            n_iter=self.n_iterations,
            scoring="f1_weighted",
            cv=tscv,
            n_jobs=-1,
            random_state=42,
            verbose=1,
        )

        search.fit(X_train, y_train)

        logger.info("Best XGBoost parameters found!")
        logger.info(f"   Score: {search.best_score_:.4f}")
        logger.info(f"   Params: {search.best_params_}")

        return {
            "best_params": search.best_params_,
            "best_score": float(search.best_score_),
            "model": "xgboost",
        }

    def optimize_lightgbm(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        search_space: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Optimizes LightGBM hyperparameters.

        Args:
            X_train: Training features
            y_train: Training labels (0, 1, 2)
            search_space: Optional custom search space

        Returns:
            Dict with best parameters and score
        """
        import lightgbm as lgb
        from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit

        logger.info("Starting LightGBM hyperparameter search...")

        space = search_space or self.LIGHTGBM_SEARCH_SPACE
        base_model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            metric="multi_logloss",
            random_state=42,
            n_jobs=-1,
            verbose=-1,
        )

        tscv = TimeSeriesSplit(n_splits=self.cv_folds)

        search = RandomizedSearchCV(
            base_model,
            space,
            n_iter=self.n_iterations,
            scoring="f1_weighted",
            cv=tscv,
            n_jobs=-1,
            random_state=42,
            verbose=1,
        )

        search.fit(X_train, y_train)

        logger.info("Best LightGBM parameters found!")
        logger.info(f"   Score: {search.best_score_:.4f}")
        logger.info(f"   Params: {search.best_params_}")

        return {
            "best_params": search.best_params_,
            "best_score": float(search.best_score_),
            "model": "lightgbm",
        }

    def optimize_all(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Optimizes XGBoost and LightGBM simultaneously.

        Args:
            X_train: Training features
            y_train: Training labels

        Returns:
            Dict with best parameters for both models
        """
        xgb_result = self.optimize_xgboost(X_train, y_train)
        lgb_result = self.optimize_lightgbm(X_train, y_train)

        return {
            "xgboost": xgb_result,
            "lightgbm": lgb_result,
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from sklearn.datasets import make_classification

    # Small test data
    X, y = make_classification(
        n_samples=500, n_features=10, n_informative=5,
        n_classes=3, random_state=42
    )

    optimizer = HyperparameterOptimizer(n_iterations=5, cv_folds=2)

    # Only test XGBoost (faster)
    result = optimizer.optimize_xgboost(X, y)
    print(f"\nBest score: {result['best_score']:.4f}")
    print(f"Best params: {result['best_params']}")

    print("\nHyperparameter optimization test successful!")
