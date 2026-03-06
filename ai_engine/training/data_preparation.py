"""
Data Preparation -- Data processing for training.

Chronological split, data balancing, and formatting
of features/labels for the ML models.
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DataPreparation:
    """
    Prepares data for ML training.

    - Chronological split (not random!)
    - Optional: Data balancing (undersampling/oversampling)
    - Feature/label separation
    """

    def __init__(
        self,
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> None:
        """
        Initializes DataPreparation.

        Args:
            train_ratio: Proportion of training data (default: 70%)
            val_ratio: Proportion of validation data (default: 15%)
            test_ratio: Proportion of test data (default: 15%)
        """
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 0.01, \
            "Ratios must sum to 1.0!"

        self.train_ratio = train_ratio
        self.val_ratio = val_ratio
        self.test_ratio = test_ratio
        logger.info(
            f"DataPreparation: Train={train_ratio:.0%}, "
            f"Val={val_ratio:.0%}, Test={test_ratio:.0%}"
        )

    def split_chronological(
        self,
        X: np.ndarray,
        y: np.ndarray,
        purge_gap: int = 60,
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Splits data chronologically WITH purging gap.

        IMPORTANT: Chronological split, NOT random!
        Older data for training, newer data for testing.

        The purging gap prevents label leakage:
        Labels at the end of the training set can look into the
        future (max_candles). The gap removes these overlapping
        data points.

        Args:
            X: Feature matrix [n_samples, n_features]
            y: Label array [n_samples]
            purge_gap: Number of candles gap between splits

        Returns:
            Dict with 'train', 'val', 'test' as Tuple (X, y)
        """
        n = len(X)
        train_end = int(n * self.train_ratio)
        val_start = train_end + purge_gap  # Gap after training
        val_end = int(n * (self.train_ratio + self.val_ratio))
        test_start = val_end + purge_gap   # Gap after validation

        # Safety check
        if test_start >= n:
            logger.warning(f"Purge gap too large, reducing")
            purge_gap = 0
            val_start = train_end
            test_start = val_end

        splits = {
            "train": (X[:train_end], y[:train_end]),
            "val": (X[val_start:val_end], y[val_start:val_end]),
            "test": (X[test_start:], y[test_start:]),
        }

        for name, (Xi, yi) in splits.items():
            logger.info(
                f"  {name}: {len(Xi)} samples "
                f"(BUY={np.sum(yi == 1)}, SELL={np.sum(yi == -1)}, HOLD={np.sum(yi == 0)})"
            )
        if purge_gap > 0:
            logger.info(f"  Purging gap: {purge_gap} candles between splits")

        return splits

    def prepare_features_labels(
        self,
        df: pd.DataFrame,
        feature_names: List[str],
        label_column: str = "label",
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Separates features and labels from a DataFrame.

        Args:
            df: DataFrame with feature columns and label column
            feature_names: List of feature column names
            label_column: Name of the label column

        Returns:
            Tuple (X, y) as numpy arrays
        """
        # Check if all features are present
        missing = [f for f in feature_names if f not in df.columns]
        if missing:
            logger.warning(f"Missing features: {missing}")
            for feat in missing:
                df[feat] = 0.0

        X = df[feature_names].values.astype(np.float32)
        y = df[label_column].values.astype(int)

        # Check for NaN/Inf
        nan_count = np.isnan(X).sum()
        inf_count = np.isinf(X).sum()
        if nan_count > 0:
            logger.warning(f"{nan_count} NaN values in features -- setting to 0.0")
            X = np.nan_to_num(X, nan=0.0)
        if inf_count > 0:
            logger.warning(f"{inf_count} Inf values in features -- setting to 0.0")
            X = np.nan_to_num(X, posinf=0.0, neginf=0.0)

        logger.info(f"Features: {X.shape}, Labels: {y.shape}")
        return X, y

    def balance_classes(
        self,
        X: np.ndarray,
        y: np.ndarray,
        strategy: str = "undersample",
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Balances classes through under- or oversampling.

        Args:
            X: Feature matrix
            y: Labels
            strategy: 'undersample' or 'oversample'

        Returns:
            Balanced (X, y)
        """
        classes, counts = np.unique(y, return_counts=True)
        logger.info(f"Classes before balancing: {dict(zip(classes, counts))}")

        if strategy == "undersample":
            min_count = counts.min()
            indices = []
            for cls in classes:
                cls_indices = np.where(y == cls)[0]
                selected = np.random.choice(cls_indices, min_count, replace=False)
                indices.extend(selected)
        elif strategy == "oversample":
            max_count = counts.max()
            indices = []
            for cls in classes:
                cls_indices = np.where(y == cls)[0]
                if len(cls_indices) < max_count:
                    extra = np.random.choice(cls_indices, max_count - len(cls_indices), replace=True)
                    indices.extend(cls_indices)
                    indices.extend(extra)
                else:
                    indices.extend(cls_indices)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        indices = sorted(indices)  # Maintain chronological order
        X_balanced = X[indices]
        y_balanced = y[indices]

        classes_after, counts_after = np.unique(y_balanced, return_counts=True)
        logger.info(f"Classes after {strategy}: {dict(zip(classes_after, counts_after))}")

        return X_balanced, y_balanced

    def remove_warmup_period(
        self,
        df: pd.DataFrame,
        warmup_candles: int = 200,
    ) -> pd.DataFrame:
        """
        Removes the warmup period (needed for indicator calculation).

        Args:
            df: DataFrame with calculated features
            warmup_candles: Number of candles to remove

        Returns:
            DataFrame without warmup period
        """
        if len(df) <= warmup_candles:
            logger.warning(f"DataFrame has only {len(df)} rows, warmup={warmup_candles}!")
            return df

        df_clean = df.iloc[warmup_candles:].reset_index(drop=True)
        logger.info(f"Warmup removed: {warmup_candles} candles -- {len(df_clean)} remaining")
        return df_clean


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Test
    np.random.seed(42)
    n = 1000
    X = np.random.randn(n, 20)
    y = np.random.choice([-1, 0, 1], n, p=[0.2, 0.5, 0.3])

    dp = DataPreparation()

    # Chronological split
    splits = dp.split_chronological(X, y)
    print(f"\nTrain: {splits['train'][0].shape}")
    print(f"Val: {splits['val'][0].shape}")
    print(f"Test: {splits['test'][0].shape}")

    # Balancing
    X_bal, y_bal = dp.balance_classes(X, y, strategy="undersample")
    print(f"\nBalanced: {X_bal.shape}")

    print("\nDataPreparation test successful!")
