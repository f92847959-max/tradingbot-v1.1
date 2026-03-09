"""
Feature Scaler -- Feature normalization.

Wrapper around sklearn StandardScaler with save/load functionality.
"""

import logging
import os
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class FeatureScaler:
    """
    Wrapper around sklearn StandardScaler for feature normalization.

    Normalizes features to mean=0 and standard deviation=1.
    Can save/load the scaler for consistent scaling
    between training and prediction.
    """

    def __init__(self) -> None:
        """Initializes the FeatureScaler."""
        self._scaler: StandardScaler = StandardScaler()
        self._feature_names: List[str] = []
        self._is_fitted: bool = False

    @property
    def is_fitted(self) -> bool:
        """Returns whether the scaler has already been fitted."""
        return self._is_fitted

    def fit(self, df: pd.DataFrame, feature_names: List[str]) -> None:
        """
        Fits the scaler on the training data.

        Args:
            df: DataFrame with the feature columns
            feature_names: List of feature column names to be scaled
        """
        self._feature_names = feature_names.copy()
        features = df[feature_names].values
        self._scaler.fit(features)
        self._is_fitted = True
        logger.info(f"Scaler fitted on {len(feature_names)} features, {len(df)} samples")

    def fit_transform(self, df: pd.DataFrame, feature_names: List[str]) -> pd.DataFrame:
        """
        Fits the scaler and transforms the data.

        Args:
            df: DataFrame with the feature columns
            feature_names: List of feature column names

        Returns:
            DataFrame with scaled feature columns
        """
        self.fit(df, feature_names)
        return self.transform(df)

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transforms the features with the fitted scaler.

        Args:
            df: DataFrame with the feature columns

        Returns:
            DataFrame with scaled feature columns

        Raises:
            RuntimeError: If the scaler has not been fitted yet
        """
        if not self._is_fitted:
            raise RuntimeError("Scaler must be fitted first! Call fit() or fit_transform().")

        df = df.copy()

        # Check if all expected features are present
        missing = [f for f in self._feature_names if f not in df.columns]
        if missing:
            logger.warning(f"Missing features during transform: {missing}")
            for feat in missing:
                df[feat] = 0.0

        features = df[self._feature_names].values
        scaled = self._scaler.transform(features)
        df[self._feature_names] = scaled

        return df

    def inverse_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Reverses the scaling.

        Args:
            df: DataFrame with scaled feature columns

        Returns:
            DataFrame with original-scaled feature columns
        """
        if not self._is_fitted:
            raise RuntimeError("Scaler is not fitted!")

        df = df.copy()
        features = df[self._feature_names].values
        original = self._scaler.inverse_transform(features)
        df[self._feature_names] = original
        return df

    def save(self, path: str) -> None:
        """
        Saves the scaler as a .pkl file.

        Args:
            path: File path for the .pkl file
        """
        if not self._is_fitted:
            raise RuntimeError("Scaler is not fitted -- nothing to save!")

        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        data = {
            "scaler": self._scaler,
            "feature_names": self._feature_names,
        }
        joblib.dump(data, path)
        logger.info(f"Scaler saved: {path}")

    def load(self, path: str) -> None:
        """
        Loads a saved scaler.

        Args:
            path: File path of the .pkl file

        Raises:
            FileNotFoundError: If the file does not exist
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Scaler file not found: {path}")

        data = joblib.load(path)
        self._scaler = data["scaler"]
        self._feature_names = data["feature_names"]
        self._is_fitted = True
        logger.info(f"Scaler loaded: {path} ({len(self._feature_names)} features)")

    def get_feature_names(self) -> List[str]:
        """Returns the list of feature names."""
        return self._feature_names.copy()

    def get_stats(self) -> Optional[pd.DataFrame]:
        """
        Returns the mean and standard deviation per feature.

        Returns:
            DataFrame with mean and std per feature, or None if not fitted
        """
        if not self._is_fitted:
            return None

        return pd.DataFrame({
            "feature": self._feature_names,
            "mean": np.asarray(self._scaler.mean_),
            "std": np.sqrt(np.asarray(self._scaler.var_)),
        })


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Test
    np.random.seed(42)
    n = 100
    features = ["feature_a", "feature_b", "feature_c"]
    df = pd.DataFrame({
        "feature_a": np.random.randn(n) * 10 + 50,
        "feature_b": np.random.randn(n) * 0.001,
        "feature_c": np.random.uniform(0, 100, n),
        "other_col": np.random.randn(n),
    })

    scaler = FeatureScaler()

    # Fit + Transform
    scaled_df = scaler.fit_transform(df, features)
    print(f"Scaler fitted")
    print(f"Before scaling:\n{df[features].describe().round(2)}")
    print(f"After scaling:\n{scaled_df[features].describe().round(2)}")

    # Stats
    stats = scaler.get_stats()
    print(f"\nScaler stats:\n{stats}")

    # Save + Load
    test_path = "test_scaler.pkl"
    scaler.save(test_path)

    scaler2 = FeatureScaler()
    scaler2.load(test_path)
    print(f"\nScaler loaded: {scaler2.get_feature_names()}")

    # Cleanup
    os.remove(test_path)
    print("Test file cleaned up")
