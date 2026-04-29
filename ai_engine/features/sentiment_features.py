"""Sentiment feature block for ML input."""

from __future__ import annotations

from typing import Any, List

import numpy as np
import pandas as pd


class SentimentFeatures:
    """Add news sentiment columns to candle feature frames."""

    FEATURE_NAMES: List[str] = [
        "sent_1h",
        "sent_4h",
        "sent_24h",
        "sent_momentum",
        "sent_divergence",
        "news_count_1h",
    ]

    def __init__(self, aggregator: Any | None = None) -> None:
        self._aggregator = aggregator

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        values = self._zero_features()
        if self._aggregator is not None and not result.empty:
            latest_ts = self._latest_timestamp(result)
            if latest_ts is not None:
                values.update(self._aggregator.get_features_at(latest_ts, window_records=None))
                values["sent_divergence"] = self._sentiment_divergence(result, values["sent_1h"])

        for name in self.FEATURE_NAMES:
            result[name] = float(values.get(name, 0.0))
        return result

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()

    def _latest_timestamp(self, df: pd.DataFrame) -> pd.Timestamp | None:
        if isinstance(df.index, pd.DatetimeIndex):
            return pd.Timestamp(df.index[-1])
        if "timestamp" in df.columns:
            return pd.Timestamp(df["timestamp"].iloc[-1])
        return None

    def _sentiment_divergence(self, df: pd.DataFrame, sent_1h: float) -> float:
        if len(df) < 2 or "close" not in df.columns:
            return 0.0
        delta = float(df["close"].iloc[-1]) - float(df["close"].iloc[-2])
        price_direction = float(np.sign(delta))
        return max(-1.0, min(1.0, float(sent_1h) - price_direction))

    def _zero_features(self) -> dict[str, float]:
        return {name: 0.0 for name in self.FEATURE_NAMES}
