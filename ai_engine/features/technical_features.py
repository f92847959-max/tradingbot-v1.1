"""
Technical Features -- Derived features from indicators.

Calculates features like RSI zone, MACD cross, EMA trend, etc.
from the already calculated technical indicators.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalFeatures:
    """Generates derived features from technical indicators."""

    # List of all feature columns this class generates
    FEATURE_NAMES: List[str] = [
        "rsi_zone",
        "macd_cross",
        "ema_trend",
        "ema_distance_9_21",
        "ema_above_50",
        "ema_above_200",
        "bb_squeeze",
        "adx_trending",
        "stoch_cross",
        "stoch_zone",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all technical features.

        Args:
            df: DataFrame with OHLCV + technical indicators
                Expected columns: rsi_14, macd_line, macd_signal, macd_hist,
                ema_9, ema_21, ema_50, ema_200, bb_width, adx_14,
                stoch_k, stoch_d

        Returns:
            DataFrame with additional technical feature columns
        """
        df = df.copy()
        logger.debug("Calculating technical features...")

        # --- RSI Zone ---
        # -1 = oversold (<30), 0 = neutral, 1 = overbought (>70)
        if "rsi_14" in df.columns:
            df["rsi_zone"] = 0
            df.loc[df["rsi_14"] < 30, "rsi_zone"] = -1
            df.loc[df["rsi_14"] > 70, "rsi_zone"] = 1
        else:
            df["rsi_zone"] = 0

        # --- MACD Crossover ---
        # 1 = bullish cross, -1 = bearish cross, 0 = no cross
        if "macd_line" in df.columns and "macd_signal" in df.columns:
            macd_diff = df["macd_line"] - df["macd_signal"]
            macd_diff_prev = macd_diff.shift(1)
            df["macd_cross"] = 0
            # Bullish: previously below signal, now above
            df.loc[(macd_diff_prev <= 0) & (macd_diff > 0), "macd_cross"] = 1
            # Bearish: previously above signal, now below
            df.loc[(macd_diff_prev >= 0) & (macd_diff < 0), "macd_cross"] = -1
        else:
            df["macd_cross"] = 0

        # --- EMA Trend ---
        # 1 when EMA9 > EMA21 (bullish), -1 when EMA9 < EMA21 (bearish)
        if "ema_9" in df.columns and "ema_21" in df.columns:
            df["ema_trend"] = np.where(df["ema_9"] > df["ema_21"], 1, -1)
        else:
            df["ema_trend"] = 0

        # --- EMA Distance 9/21 ---
        # Distance between EMA9 and EMA21 in pips (Gold pip = 0.01)
        if "ema_9" in df.columns and "ema_21" in df.columns:
            df["ema_distance_9_21"] = (df["ema_9"] - df["ema_21"]) / 0.01
        else:
            df["ema_distance_9_21"] = 0.0

        # --- EMA Above 50 ---
        # 1 when Close > EMA50, otherwise -1
        if "ema_50" in df.columns and "close" in df.columns:
            df["ema_above_50"] = np.where(df["close"] > df["ema_50"], 1, -1)
        else:
            df["ema_above_50"] = 0

        # --- EMA Above 200 ---
        # 1 when Close > EMA200, otherwise -1
        if "ema_200" in df.columns and "close" in df.columns:
            df["ema_above_200"] = np.where(df["close"] > df["ema_200"], 1, -1)
        else:
            df["ema_above_200"] = 0

        # --- Bollinger Band Squeeze ---
        # True when BB width is in the tightest 10% (breakout imminent)
        if "bb_width" in df.columns:
            bb_threshold = df["bb_width"].rolling(window=50, min_periods=10).quantile(0.1)
            df["bb_squeeze"] = (df["bb_width"] < bb_threshold).astype(int)
        else:
            df["bb_squeeze"] = 0

        # --- ADX Trending ---
        # 1 when ADX > 25 (strong trend), otherwise 0
        if "adx_14" in df.columns:
            df["adx_trending"] = (df["adx_14"] > 25).astype(int)
        else:
            df["adx_trending"] = 0

        # --- Stochastic Crossover ---
        # 1 = bullish cross (K crosses D upward), -1 = bearish cross
        if "stoch_k" in df.columns and "stoch_d" in df.columns:
            stoch_diff = df["stoch_k"] - df["stoch_d"]
            stoch_diff_prev = stoch_diff.shift(1)
            df["stoch_cross"] = 0
            df.loc[(stoch_diff_prev <= 0) & (stoch_diff > 0), "stoch_cross"] = 1
            df.loc[(stoch_diff_prev >= 0) & (stoch_diff < 0), "stoch_cross"] = -1
        else:
            df["stoch_cross"] = 0

        # --- Stochastic Zone ---
        # -1 = oversold (<20), 0 = neutral, 1 = overbought (>80)
        if "stoch_k" in df.columns:
            df["stoch_zone"] = 0
            df.loc[df["stoch_k"] < 20, "stoch_zone"] = -1
            df.loc[df["stoch_k"] > 80, "stoch_zone"] = 1
        else:
            df["stoch_zone"] = 0

        logger.debug(f"Technical features calculated: {len(self.FEATURE_NAMES)} columns")
        return df

    def get_feature_names(self) -> List[str]:
        """Returns the list of all feature column names."""
        return self.FEATURE_NAMES.copy()


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.DEBUG)

    # Create synthetic data
    np.random.seed(42)
    n = 100
    test_df = pd.DataFrame({
        "close": 2045 + np.cumsum(np.random.randn(n) * 0.5),
        "rsi_14": np.random.uniform(20, 80, n),
        "macd_line": np.random.randn(n) * 0.5,
        "macd_signal": np.random.randn(n) * 0.3,
        "macd_hist": np.random.randn(n) * 0.2,
        "ema_9": 2045 + np.cumsum(np.random.randn(n) * 0.3),
        "ema_21": 2045 + np.cumsum(np.random.randn(n) * 0.2),
        "ema_50": 2045 + np.cumsum(np.random.randn(n) * 0.1),
        "ema_200": np.full(n, 2040.0),
        "bb_width": np.random.uniform(0.005, 0.02, n),
        "adx_14": np.random.uniform(10, 50, n),
        "stoch_k": np.random.uniform(10, 90, n),
        "stoch_d": np.random.uniform(10, 90, n),
    })

    tf = TechnicalFeatures()
    result = tf.calculate(test_df)
    print(f"Technical features: {tf.get_feature_names()}")
    print(f"DataFrame shape: {result.shape}")
    print(result[tf.get_feature_names()].describe())
