"""
Price Features -- Price-based and candle features.

Calculates price changes, candle body/wick ratios,
consecutive direction counters, and candlestick patterns.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PriceFeatures:
    """Generates price-based and candle features."""

    FEATURE_NAMES: List[str] = [
        # Price changes
        "price_change_1",
        "price_change_3",
        "price_change_5",
        "price_change_10",
        "price_change_pct_1",
        # High/Low distances
        "highest_high_10",
        "lowest_low_10",
        "distance_to_high_10",
        "distance_to_low_10",
        # Candle features
        "body_size",
        "upper_wick_ratio",
        "lower_wick_ratio",
        "is_bullish_candle",
        "consecutive_bullish",
        "consecutive_bearish",
        # Candle patterns
        "is_doji",
        "is_hammer",
        "is_shooting_star",
        "is_engulfing_bull",
        "is_engulfing_bear",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all price and candle features.

        Args:
            df: DataFrame with OHLCV data.
                Expected columns: open, high, low, close

        Returns:
            DataFrame with additional price feature columns
        """
        df = df.copy()
        logger.debug("Calculating price features...")

        close = df["close"]
        open_ = df["open"]
        high = df["high"]
        low = df["low"]

        # --- Price changes ---
        df["price_change_1"] = close - close.shift(1)
        df["price_change_3"] = close - close.shift(3)
        df["price_change_5"] = close - close.shift(5)
        df["price_change_10"] = close - close.shift(10)
        df["price_change_pct_1"] = (df["price_change_1"] / close.shift(1)) * 100

        # --- High/Low distances ---
        df["highest_high_10"] = high.rolling(window=10, min_periods=1).max()
        df["lowest_low_10"] = low.rolling(window=10, min_periods=1).min()
        df["distance_to_high_10"] = df["highest_high_10"] - close
        df["distance_to_low_10"] = close - df["lowest_low_10"]

        # --- Candle features ---
        candle_range = high - low + 0.0001  # epsilon to avoid division by zero
        body = close - open_
        body_abs = body.abs()

        df["body_size"] = body_abs
        df["upper_wick_ratio"] = (high - np.maximum(open_, close)) / candle_range
        df["lower_wick_ratio"] = (np.minimum(open_, close) - low) / candle_range
        df["is_bullish_candle"] = (close > open_).astype(int)

        # --- Consecutive direction ---
        df["consecutive_bullish"] = self._count_consecutive(df["is_bullish_candle"] == 1)
        df["consecutive_bearish"] = self._count_consecutive(df["is_bullish_candle"] == 0)

        # --- Candle patterns ---
        upper_wick = high - np.maximum(open_, close)
        lower_wick = np.minimum(open_, close) - low
        is_bullish = close > open_
        is_bearish = close < open_

        # Doji: body < 10% of total candle
        df["is_doji"] = (body_abs < candle_range * 0.1).astype(int)

        # Hammer: long lower wick, short upper wick, bullish
        df["is_hammer"] = (
            (lower_wick > body_abs * 2)
            & (upper_wick < body_abs * 0.5)
            & is_bullish
        ).astype(int)

        # Shooting star: long upper wick, short lower wick, bearish
        df["is_shooting_star"] = (
            (upper_wick > body_abs * 2)
            & (lower_wick < body_abs * 0.5)
            & is_bearish
        ).astype(int)

        # Bullish engulfing: current close > previous open, current open < previous close
        prev_open = open_.shift(1)
        prev_close = close.shift(1)
        prev_bearish = prev_close < prev_open

        df["is_engulfing_bull"] = (
            (close > prev_open)
            & (open_ < prev_close)
            & prev_bearish
            & is_bullish
        ).astype(int)

        # Bearish engulfing: current close < previous open, current open > previous close
        prev_bullish = prev_close > prev_open

        df["is_engulfing_bear"] = (
            (close < prev_open)
            & (open_ > prev_close)
            & prev_bullish
            & is_bearish
        ).astype(int)

        logger.debug(f"Price features calculated: {len(self.FEATURE_NAMES)} columns")
        return df

    @staticmethod
    def _count_consecutive(condition: pd.Series) -> pd.Series:
        """
        Counts consecutive True values in a boolean Series.

        Args:
            condition: Boolean Series

        Returns:
            Series with the count of consecutive True values
        """
        # Form groups: new group at each change
        groups = (~condition).cumsum()
        # Count within each group
        consecutive = condition.groupby(groups).cumsum()
        return consecutive.fillna(0).astype(int)

    def get_feature_names(self) -> List[str]:
        """Returns the list of all feature column names."""
        return self.FEATURE_NAMES.copy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    np.random.seed(42)
    n = 100
    base = 2045 + np.cumsum(np.random.randn(n) * 0.5)
    test_df = pd.DataFrame({
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.5,
        "low": base - np.abs(np.random.randn(n)) * 0.5,
        "close": base,
    })

    pf = PriceFeatures()
    result = pf.calculate(test_df)
    print(f"Price features: {pf.get_feature_names()}")
    print(f"DataFrame shape: {result.shape}")
    print(f"Doji detected: {result['is_doji'].sum()}")
    print(f"Hammer detected: {result['is_hammer'].sum()}")
    print(f"Bullish engulfing: {result['is_engulfing_bull'].sum()}")
