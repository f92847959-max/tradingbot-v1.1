"""
Feature Engineer -- Main feature engineering orchestrator.

Combines all feature groups (technical, price, time, gold-specific)
into a unified feature set of ~60 features.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from shared.utils import cleanup_dataframe_features
from .technical_features import TechnicalFeatures
from .price_features import PriceFeatures
from .time_features import TimeFeatures
from .gold_specific import GoldSpecificFeatures
from .market_structure_liquidity import MarketStructureLiquidityFeatures
from .microstructure_features import MicrostructureFeatures
from .orderflow_features import OrderFlowFeatures
from .support_resistance import SupportResistanceFeatures
from .correlation_features import CorrelationFeatures
from correlation.snapshot import CorrelationSnapshot

logger = logging.getLogger(__name__)


@dataclass
class FeatureCache:
    """Cache for computed features to avoid redundant recalculation.

    Stores the last computed features along with the timestamp of the most
    recent candle used. If the latest candle timestamp hasn't changed, the
    cached features are returned directly.
    """

    last_candle_timestamp: Optional[pd.Timestamp] = None
    last_candle_close: Optional[float] = None
    last_timeframe: Optional[str] = None
    cached_df: Optional[pd.DataFrame] = None
    hits: int = 0
    misses: int = 0
    last_updated: float = 0.0

    def is_valid(
        self,
        df: pd.DataFrame,
        timeframe: str,
    ) -> bool:
        """Check if cached features are still valid for this data.

        Cache is keyed on candle timestamp only (not close price) to avoid
        invalidation on every tick within the same candle.
        """
        if self.cached_df is None or self.last_candle_timestamp is None:
            return False

        if self.last_timeframe != timeframe:
            return False

        if df.empty:
            return False

        # Check if the latest candle timestamp is the same
        latest_ts = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else df.iloc[-1].get("timestamp")

        if latest_ts != self.last_candle_timestamp:
            return False

        return True

    def update(
        self,
        df: pd.DataFrame,
        result_df: pd.DataFrame,
        timeframe: str,
    ) -> None:
        """Store new computed features in cache."""
        if df.empty:
            return

        latest_ts = df.index[-1] if isinstance(df.index, pd.DatetimeIndex) else df.iloc[-1].get("timestamp")
        self.last_candle_timestamp = latest_ts
        self.last_candle_close = float(df.iloc[-1]["close"])
        self.last_timeframe = timeframe
        self.cached_df = result_df.copy()
        self.last_updated = time.monotonic()
        self.misses += 1

    def get(self) -> pd.DataFrame:
        """Return cached features."""
        self.hits += 1
        if self.cached_df is None:
            raise RuntimeError("Cache is empty")
        return self.cached_df.copy()

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100.0) if total > 0 else 0.0


class FeatureEngineer:
    """
    Main feature engineering class.

    Orchestrates all feature groups and produces ~60 features
    from raw OHLCV data + technical indicators.
    """

    def __init__(self) -> None:
        """Initialize the FeatureEngineer with all sub-feature calculators."""
        self._technical = TechnicalFeatures()
        self._price = PriceFeatures()
        self._time = TimeFeatures()
        self._gold = GoldSpecificFeatures()
        self._micro = MicrostructureFeatures()
        self._orderflow = OrderFlowFeatures()
        self._sr = SupportResistanceFeatures()
        self._correlation = CorrelationFeatures()
        self._specialist = MarketStructureLiquidityFeatures()

        # Combined feature list
        self._feature_names: List[str] = (
            self._technical.get_feature_names()
            + self._price.get_feature_names()
            + self._time.get_feature_names()
            + self._gold.get_feature_names()
            + self._micro.get_feature_names()
            + self._orderflow.get_feature_names()
            + self._sr.get_feature_names()
            + self._correlation.get_feature_names()
        )
        self._specialist_feature_names: List[str] = (
            self._specialist.get_feature_names()
        )

        # Feature cache for avoiding redundant recalculation
        self._cache = FeatureCache()

        logger.info(f"FeatureEngineer initialized with {len(self._feature_names)} features")

    def create_features(
        self,
        df: pd.DataFrame,
        timeframe: str = "5m",
        multi_tf_data: Optional[Dict[str, pd.DataFrame]] = None,
        correlation_snapshot: Optional[CorrelationSnapshot] = None,
        include_specialist: bool = False,
    ) -> pd.DataFrame:
        """
        Create ALL features from a DataFrame with OHLCV + indicators.

        Args:
            df: DataFrame with columns: open, high, low, close, volume
                + technical indicators (rsi_14, macd_line, ema_9, etc.)
            timeframe: The timeframe of the data (e.g. '1m', '5m', '15m')
            multi_tf_data: Optional dict with multi-timeframe data
                e.g. {"1m": df_1m, "5m": df_5m, "15m": df_15m}
            correlation_snapshot: Optional inter-market snapshot to broadcast
                into the feature matrix for this call.

        Returns:
            DataFrame with ~60 additional feature columns.
            All NaN values are filled with 0.0.
            All bool values are converted to int (0/1).
        """
        # Check cache first (skip recalculation if OHLCV unchanged)
        if (
            self._cache.is_valid(df, timeframe)
            and multi_tf_data is None
            and correlation_snapshot is None
            and not include_specialist
        ):
            logger.debug(
                "Feature cache HIT for %s (hit rate: %.1f%%)",
                timeframe, self._cache.hit_rate,
            )
            return self._cache.get()

        logger.info(f"Creating features for timeframe {timeframe} "
                     f"({len(df)} candles)...")

        # Check required columns
        required = ["open", "high", "low", "close"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # 1. Technical features (derived from indicators)
        df = self._technical.calculate(df)

        # 2. Price and candle features
        df = self._price.calculate(df)

        # 3. Time features
        df = self._time.calculate(df)

        # 4. Gold-specific features
        df = self._gold.calculate(df)
        df = self._micro.calculate(df)
        df = self._orderflow.calculate(df)
        df = self._sr.calculate(df)
        df = self._correlation.calculate(df, correlation_snapshot)
        if include_specialist:
            df = self._specialist.calculate(df)

        # 5. Multi-timeframe features (if available)
        if multi_tf_data:
            df = self._add_multi_tf_features(df, multi_tf_data)

        # 6. Cleanup: NaN -> 0.0, bool -> int
        feature_names = self.get_feature_names(include_specialist=include_specialist)
        df = self._cleanup_features(df, feature_names)

        feature_count = len([c for c in feature_names if c in df.columns])
        logger.info(f"{feature_count} features created for {timeframe}")

        # Update cache (only for single-timeframe to avoid MTF staleness)
        if multi_tf_data is None and correlation_snapshot is None:
            self._cache.update(df, df, timeframe)
            logger.debug(
                "Feature cache updated (hit rate: %.1f%%)", self._cache.hit_rate,
            )

        return df

    def _add_multi_tf_features(
        self,
        df: pd.DataFrame,
        multi_tf_data: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Add multi-timeframe features.

        Calculates the trend across different timeframes and whether
        all timeframes are aligned.

        Args:
            df: Main DataFrame
            multi_tf_data: Dict with DataFrames per timeframe

        Returns:
            DataFrame with multi-TF features
        """
        mt_feature_names = []

        for tf_name, tf_df in multi_tf_data.items():
            trend_col = f"trend_{tf_name}"
            rsi_col = f"rsi_{tf_name}"

            # Trend based on EMA 9 vs EMA 21
            if "ema_9" in tf_df.columns and "ema_21" in tf_df.columns:
                latest = tf_df.iloc[-1] if len(tf_df) > 0 else None
                if latest is not None:
                    trend = 1 if latest["ema_9"] > latest["ema_21"] else -1
                    df[trend_col] = trend
                else:
                    df[trend_col] = 0
            else:
                df[trend_col] = 0

            mt_feature_names.append(trend_col)

            # RSI from other timeframe
            if "rsi_14" in tf_df.columns:
                latest_rsi = tf_df["rsi_14"].iloc[-1] if len(tf_df) > 0 else 50.0
                df[rsi_col] = latest_rsi
            else:
                df[rsi_col] = 50.0

            mt_feature_names.append(rsi_col)

        # Timeframe alignment: all trends the same?
        trend_cols = [c for c in df.columns if c.startswith("trend_")]
        if len(trend_cols) >= 2:
            first_trend = df[trend_cols[0]]
            df["tf_alignment"] = 1
            for tc in trend_cols[1:]:
                df["tf_alignment"] = df["tf_alignment"] & (df[tc] == first_trend)
            df["tf_alignment"] = df["tf_alignment"].astype(int)
        else:
            df["tf_alignment"] = 0

        mt_feature_names.append("tf_alignment")

        # Update feature names
        for feat in mt_feature_names:
            if feat not in self._feature_names:
                self._feature_names.append(feat)

        logger.debug(f"Multi-TF features added: {mt_feature_names}")
        return df

    def _cleanup_features(
        self,
        df: pd.DataFrame,
        feature_names: List[str],
    ) -> pd.DataFrame:
        """
        Clean up the feature DataFrame.

        - All NaN values -> 0.0
        - All bool columns -> int (0/1)
        - Inf values -> 0.0

        Args:
            df: DataFrame with features

        Returns:
            Cleaned DataFrame
        """
        # Bool -> int
        bool_cols = df.select_dtypes(include=["bool"]).columns
        for col in bool_cols:
            df[col] = df[col].astype(int)

        # Centralized Inf -> NaN -> 0 cleanup for feature columns
        feature_cols = [c for c in feature_names if c in df.columns]
        df = cleanup_dataframe_features(df, feature_cols)

        return df

    def get_feature_names(self, include_specialist: bool = False) -> List[str]:
        """
        Return the list of all feature column names.

        Returns:
            List of feature names (used for feature importance)
        """
        names = self._feature_names.copy()
        if include_specialist:
            names += self._specialist_feature_names
        return names

    def get_specialist_feature_names(self) -> List[str]:
        """Return the opt-in specialist feature list."""
        return self._specialist_feature_names.copy()

    @property
    def cache(self) -> FeatureCache:
        """Access the feature cache (for monitoring)."""
        return self._cache

    def get_feature_groups(self) -> Dict[str, List[str]]:
        """
        Return features grouped by category.

        Returns:
            Dict with feature groups
        """
        return {
            "technical": self._technical.get_feature_names(),
            "price": self._price.get_feature_names(),
            "time": self._time.get_feature_names(),
            "gold_specific": self._gold.get_feature_names(),
            "microstructure": self._micro.get_feature_names(),
            "orderflow": self._orderflow.get_feature_names(),
            "support_resistance": self._sr.get_feature_names(),
            "correlation": self._correlation.get_feature_names(),
            "market_structure_liquidity": self._specialist.get_feature_names(),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Synthetic test data
    np.random.seed(42)
    n = 200
    base = 2045 + np.cumsum(np.random.randn(n) * 0.5)
    timestamps = pd.date_range("2026-02-19 08:00", periods=n, freq="5min", tz="UTC")

    test_df = pd.DataFrame({
        "timestamp": timestamps,
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.5,
        "low": base - np.abs(np.random.randn(n)) * 0.5,
        "close": base,
        "volume": np.random.randint(500, 2000, n),
        # Simulated indicators
        "rsi_14": np.random.uniform(20, 80, n),
        "macd_line": np.random.randn(n) * 0.5,
        "macd_signal": np.random.randn(n) * 0.3,
        "macd_hist": np.random.randn(n) * 0.2,
        "ema_9": base + np.random.randn(n) * 0.3,
        "ema_21": base + np.random.randn(n) * 0.2,
        "ema_50": base + np.random.randn(n) * 0.1,
        "ema_200": np.full(n, 2040.0),
        "bb_width": np.random.uniform(0.005, 0.02, n),
        "bb_position": np.random.uniform(0, 1, n),
        "adx_14": np.random.uniform(10, 50, n),
        "atr_14": np.random.uniform(0.5, 2.0, n),
        "stoch_k": np.random.uniform(10, 90, n),
        "stoch_d": np.random.uniform(10, 90, n),
        "pivot": np.full(n, 2045.0),
        "pivot_s1": np.full(n, 2040.0),
        "pivot_r1": np.full(n, 2050.0),
        "vwap": np.full(n, 2046.0),
    }, index=timestamps)

    # Feature Engineering
    fe = FeatureEngineer()
    result = fe.create_features(test_df, timeframe="5m")

    print(f"\nResult: {result.shape[0]} rows x {result.shape[1]} columns")
    print(f"Feature names ({len(fe.get_feature_names())}):")
    for group, features in fe.get_feature_groups().items():
        print(f"  {group}: {len(features)} features")
    print(f"\nAll features created! No NaN: {result[fe.get_feature_names()].isna().sum().sum() == 0}")

