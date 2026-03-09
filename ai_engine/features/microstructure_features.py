"""
Microstructure features for L1/L2 market context.

Uses optional columns from live/synthetic feeds:
- l1_spread_pips
- l2_order_imbalance
- l2_depth_ratio
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
from shared.utils import cleanup_dataframe_features
import pandas as pd

logger = logging.getLogger(__name__)


class MicrostructureFeatures:
    """Builds robust microstructure-derived features."""

    FEATURE_NAMES: List[str] = [
        "l1_spread_pips",
        "l1_spread_change_1",
        "l1_spread_zscore_50",
        "l2_order_imbalance",
        "l2_order_imbalance_ema_10",
        "l2_imbalance_abs",
        "l2_depth_ratio",
        "l2_depth_ratio_log",
        "l2_depth_ratio_zscore_50",
        "micro_pressure",
        "micro_liquidity_stress",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Adds microstructure features. Missing source columns are handled safely."""
        out = df.copy()

        spread = _series_or_default(out, "l1_spread_pips", 1.0)
        imbalance = _series_or_default(out, "l2_order_imbalance", 0.0)
        depth = _series_or_default(out, "l2_depth_ratio", 1.0)

        spread = spread.clip(lower=0.01)
        imbalance = imbalance.clip(lower=-1.0, upper=1.0)
        depth = depth.clip(lower=0.05, upper=25.0)

        out["l1_spread_pips"] = spread
        out["l1_spread_change_1"] = spread.diff()
        out["l1_spread_zscore_50"] = _rolling_zscore(spread, window=50)

        out["l2_order_imbalance"] = imbalance
        out["l2_order_imbalance_ema_10"] = imbalance.ewm(span=10, adjust=False).mean()
        out["l2_imbalance_abs"] = imbalance.abs()

        out["l2_depth_ratio"] = depth
        out["l2_depth_ratio_log"] = np.log1p(depth)
        out["l2_depth_ratio_zscore_50"] = _rolling_zscore(depth, window=50)

        out["micro_pressure"] = (
            out["l2_order_imbalance"] * (1.0 + out["l2_depth_ratio_log"]) / (1.0 + out["l1_spread_pips"])
        )
        out["micro_liquidity_stress"] = (
            out["l1_spread_pips"] * (1.0 + out["l2_imbalance_abs"]) / out["l2_depth_ratio"].clip(lower=0.05)
        )

        out = cleanup_dataframe_features(out, self.FEATURE_NAMES)

        logger.debug("Microstructure features calculated: %d columns", len(self.FEATURE_NAMES))
        return out

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=5).mean()
    std = series.rolling(window=window, min_periods=5).std().replace(0, np.nan)
    return (series - mean) / std


def _series_or_default(df: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
    else:
        series = pd.Series(default, index=df.index, dtype=float)
    return series.fillna(default)
