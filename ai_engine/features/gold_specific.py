"""
Gold-specific features -- Level-based features.

Calculates features based on pivot points, VWAP,
support/resistance, and volatility indicators.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class GoldSpecificFeatures:
    """Generates gold-specific and level-based features."""

    FEATURE_NAMES: List[str] = [
        "distance_to_pivot",
        "nearest_support",
        "nearest_resistance",
        "above_vwap",
        "current_volatility",
        "volatility_change",
        "is_high_volatility",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all gold-specific features.

        Args:
            df: DataFrame with OHLCV data and optional columns:
                pivot, pivot_s1, pivot_s2, pivot_s3,
                pivot_r1, pivot_r2, pivot_r3, vwap, atr_14

        Returns:
            DataFrame with additional gold-specific feature columns
        """
        df = df.copy()
        logger.debug("Calculating gold-specific features...")

        close = df["close"]

        # --- Pivot Point Features ---
        if "pivot" in df.columns:
            df["distance_to_pivot"] = (close - df["pivot"]) / 0.01  # in pips
        else:
            df["distance_to_pivot"] = 0.0

        # Nearest support (minimum of distances to S1, S2, S3)
        support_cols = [c for c in ["pivot_s1", "pivot_s2", "pivot_s3"] if c in df.columns]
        if support_cols:
            support_distances = pd.DataFrame()
            for col in support_cols:
                support_distances[col] = (close - df[col]).abs()
            df["nearest_support"] = support_distances.min(axis=1) / 0.01  # in pips
        else:
            df["nearest_support"] = 0.0

        # Nearest resistance (minimum of distances to R1, R2, R3)
        resistance_cols = [c for c in ["pivot_r1", "pivot_r2", "pivot_r3"] if c in df.columns]
        if resistance_cols:
            resist_distances = pd.DataFrame()
            for col in resistance_cols:
                resist_distances[col] = (close - df[col]).abs()
            df["nearest_resistance"] = resist_distances.min(axis=1) / 0.01  # in pips
        else:
            df["nearest_resistance"] = 0.0

        # --- VWAP Feature ---
        if "vwap" in df.columns:
            df["above_vwap"] = (close > df["vwap"]).astype(int)
        else:
            df["above_vwap"] = 0

        # --- Volatility Features ---
        if "atr_14" in df.columns:
            # Normalized volatility: ATR / Close x 100
            df["current_volatility"] = df["atr_14"] / close * 100

            # Volatility change vs. 60 candles ago (approx. 1 hour at 1min)
            df["volatility_change"] = df["atr_14"] / df["atr_14"].shift(60) - 1

            # Above-average volatility
            vola_mean = df["current_volatility"].rolling(window=100, min_periods=10).mean()
            df["is_high_volatility"] = (df["current_volatility"] > vola_mean).astype(int)
        else:
            df["current_volatility"] = 0.0
            df["volatility_change"] = 0.0
            df["is_high_volatility"] = 0

        logger.debug(f"Gold-specific features calculated: {len(self.FEATURE_NAMES)} columns")
        return df

    def get_feature_names(self) -> List[str]:
        """Returns the list of all feature column names."""
        return self.FEATURE_NAMES.copy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    np.random.seed(42)
    n = 200
    base = 2045 + np.cumsum(np.random.randn(n) * 0.5)
    pivot_val = 2045.0

    test_df = pd.DataFrame({
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.5,
        "low": base - np.abs(np.random.randn(n)) * 0.5,
        "close": base,
        "atr_14": np.random.uniform(0.5, 2.0, n),
        "pivot": np.full(n, pivot_val),
        "pivot_s1": np.full(n, pivot_val - 5),
        "pivot_s2": np.full(n, pivot_val - 10),
        "pivot_r1": np.full(n, pivot_val + 5),
        "pivot_r2": np.full(n, pivot_val + 10),
        "vwap": np.full(n, pivot_val + 1),
    })

    gf = GoldSpecificFeatures()
    result = gf.calculate(test_df)
    print(f"Gold features: {gf.get_feature_names()}")
    print(f"DataFrame shape: {result.shape}")
    print(result[gf.get_feature_names()].describe())
