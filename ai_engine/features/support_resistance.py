"""
Support/Resistance Features -- Swing-based dynamic S/R levels.

Computes features derived from detected swing highs/lows
(fractal-style local extrema), distances from price, proximity
flags, breakouts, and range position. Complements the
pivot-based S/R features in gold_specific.py.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class SupportResistanceFeatures:
    """Swing-based support and resistance features."""

    FEATURE_NAMES: List[str] = [
        "sr_resistance_level",
        "sr_support_level",
        "sr_dist_to_resistance",
        "sr_dist_to_support",
        "sr_dist_to_resistance_pct",
        "sr_dist_to_support_pct",
        "sr_range_position",
        "sr_near_resistance",
        "sr_near_support",
        "sr_breakout_up",
        "sr_breakout_down",
        "sr_resistance_touches",
        "sr_support_touches",
    ]

    def __init__(
        self,
        swing_window: int = 5,
        lookback: int = 50,
        proximity_atr_mult: float = 0.5,
        touch_tolerance_pct: float = 0.0015,
    ) -> None:
        self._swing_window = swing_window
        self._lookback = lookback
        self._proximity_atr_mult = proximity_atr_mult
        self._touch_tolerance_pct = touch_tolerance_pct

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        logger.debug("Calculating support/resistance features...")

        high = df["high"]
        low = df["low"]
        close = df["close"]

        swing_high = self._fractal_swing(high, is_high=True)
        swing_low = self._fractal_swing(low, is_high=False)

        resistance = swing_high.rolling(window=self._lookback, min_periods=1).max()
        support = swing_low.rolling(window=self._lookback, min_periods=1).min()

        resistance = resistance.fillna(
            high.rolling(window=self._lookback, min_periods=1).max()
        )
        support = support.fillna(
            low.rolling(window=self._lookback, min_periods=1).min()
        )

        df["sr_resistance_level"] = resistance
        df["sr_support_level"] = support

        dist_res = resistance - close
        dist_sup = close - support
        df["sr_dist_to_resistance"] = dist_res
        df["sr_dist_to_support"] = dist_sup

        safe_close = close.replace(0, np.nan)
        df["sr_dist_to_resistance_pct"] = (dist_res / safe_close) * 100
        df["sr_dist_to_support_pct"] = (dist_sup / safe_close) * 100

        rng = (resistance - support).replace(0, np.nan)
        df["sr_range_position"] = ((close - support) / rng).clip(0.0, 1.0)

        if "atr_14" in df.columns:
            tolerance = df["atr_14"] * self._proximity_atr_mult
        else:
            tolerance = close * 0.002

        df["sr_near_resistance"] = (dist_res.abs() <= tolerance).astype(int)
        df["sr_near_support"] = (dist_sup.abs() <= tolerance).astype(int)

        prev_resistance = resistance.shift(1)
        prev_support = support.shift(1)
        df["sr_breakout_up"] = (
            (close > prev_resistance) & (close.shift(1) <= prev_resistance)
        ).astype(int)
        df["sr_breakout_down"] = (
            (close < prev_support) & (close.shift(1) >= prev_support)
        ).astype(int)

        tol_price = close * self._touch_tolerance_pct
        touched_res = (high.sub(resistance).abs() <= tol_price).astype(int)
        touched_sup = (low.sub(support).abs() <= tol_price).astype(int)
        df["sr_resistance_touches"] = touched_res.rolling(
            window=self._lookback, min_periods=1,
        ).sum()
        df["sr_support_touches"] = touched_sup.rolling(
            window=self._lookback, min_periods=1,
        ).sum()

        logger.debug(
            "S/R features calculated: %d columns", len(self.FEATURE_NAMES),
        )
        return df

    def _fractal_swing(self, series: pd.Series, is_high: bool) -> pd.Series:
        w = self._swing_window
        if is_high:
            rolling = series.rolling(window=2 * w + 1, center=True).max()
        else:
            rolling = series.rolling(window=2 * w + 1, center=True).min()

        is_pivot = series == rolling
        pivots = series.where(is_pivot)
        return pivots.shift(w).ffill()

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    np.random.seed(42)
    n = 400
    base = 2045 + np.cumsum(np.random.randn(n) * 0.5)
    test_df = pd.DataFrame({
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.5,
        "low": base - np.abs(np.random.randn(n)) * 0.5,
        "close": base,
        "atr_14": np.random.uniform(0.5, 2.0, n),
    })

    sr = SupportResistanceFeatures()
    result = sr.calculate(test_df)
    print(f"S/R features: {sr.get_feature_names()}")
    print(result[sr.get_feature_names()].tail())
