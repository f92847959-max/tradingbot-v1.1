"""
Time Features -- Time-based features for trading.

Calculates trading sessions (London, New York, Overlap, Asia),
time of day, day of week, and session offset.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TimeFeatures:
    """Generates time-based trading features."""

    FEATURE_NAMES: List[str] = [
        "hour_of_day",
        "minute_of_hour",
        "day_of_week",
        "is_london_session",
        "is_ny_session",
        "is_overlap_session",
        "is_asia_session",
        "minutes_since_session_open",
        "hour_sin",
        "hour_cos",
        "day_sin",
        "day_cos",
    ]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all time-based features.

        Args:
            df: DataFrame with 'timestamp' column or DatetimeIndex.
                Timestamps should be in UTC.

        Returns:
            DataFrame with additional time feature columns
        """
        df = df.copy()
        logger.debug("Calculating time features...")

        # Extract timestamp
        if isinstance(df.index, pd.DatetimeIndex):
            ts = df.index
        elif "timestamp" in df.columns:
            ts = pd.to_datetime(df["timestamp"], utc=True)
        else:
            logger.warning("No timestamp found -- setting all time features to 0")
            for feat in self.FEATURE_NAMES:
                df[feat] = 0
            return df

        # Use .dt accessor for Series, direct access for DatetimeIndex
        _hour = ts.dt.hour if isinstance(ts, pd.Series) else ts.hour
        _minute = ts.dt.minute if isinstance(ts, pd.Series) else ts.minute
        _dow = ts.dt.dayofweek if isinstance(ts, pd.Series) else ts.dayofweek

        # --- Basic time features ---
        df["hour_of_day"] = _hour
        df["minute_of_hour"] = _minute
        df["day_of_week"] = _dow  # 0 = Monday, 4 = Friday

        # --- Session flags (UTC-based, canonical times from constants) ---
        hour = _hour

        # London: 07:00-16:30 UTC
        df["is_london_session"] = ((hour >= 7) & ((hour < 16) | ((hour == 16) & (_minute <= 30)))).astype(int)

        # New York: 13:00-22:00 UTC
        df["is_ny_session"] = ((hour >= 13) & (hour < 22)).astype(int)

        # Overlap London+NY: 13:00-16:30 UTC
        df["is_overlap_session"] = ((hour >= 13) & ((hour < 16) | ((hour == 16) & (_minute <= 30)))).astype(int)

        # Asia: 23:00-07:00 UTC
        df["is_asia_session"] = ((hour >= 23) | (hour < 7)).astype(int)

        # --- Minutes since session start ---
        # Calculate minutes since the start of the active main session
        minutes = _hour * 60 + _minute
        df["minutes_since_session_open"] = np.where(
            (hour >= 7) & ((hour < 16) | ((hour == 16) & (_minute <= 30))),
            minutes - 7 * 60,  # London start
            np.where(
                (hour >= 13) & (hour < 22),
                minutes - 13 * 60,  # NY start
                0,
            ),
        )
        df["minutes_since_session_open"] = df["minutes_since_session_open"].clip(lower=0)

        # --- Cyclical encoding ---
        # Hour: sin/cos for 24h cycle (better for ML than raw hour)
        df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        df["hour_cos"] = np.cos(2 * np.pi * hour / 24)

        # Day: sin/cos for 5-day week (Mon-Fri)
        dow = _dow
        df["day_sin"] = np.sin(2 * np.pi * dow / 5)
        df["day_cos"] = np.cos(2 * np.pi * dow / 5)

        logger.debug(f"Time features calculated: {len(self.FEATURE_NAMES)} columns")
        return df

    def get_feature_names(self) -> List[str]:
        """Return the list of all feature column names."""
        return self.FEATURE_NAMES.copy()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Synthetic data: 24 hours in 5min candles
    timestamps = pd.date_range("2026-02-19 00:00", periods=288, freq="5min", tz="UTC")
    test_df = pd.DataFrame({
        "close": 2045 + np.random.randn(288) * 0.5,
    }, index=timestamps)

    tf = TimeFeatures()
    result = tf.calculate(test_df)
    print(f"Time features: {tf.get_feature_names()}")
    print(f"London session candles: {result['is_london_session'].sum()}")
    print(f"NY session candles: {result['is_ny_session'].sum()}")
    print(f"Overlap candles: {result['is_overlap_session'].sum()}")
    print(f"Asia candles: {result['is_asia_session'].sum()}")
