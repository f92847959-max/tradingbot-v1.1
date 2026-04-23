"""
Market-structure/liquidity specialist features with causal semantics.

All event-like outputs are based on confirmed swings or shifted candle events
so historical rows do not depend on future mutations.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from shared.utils import cleanup_dataframe_features

logger = logging.getLogger(__name__)


class MarketStructureLiquidityFeatures:
    """Leakage-safe specialist feature family for structure and liquidity context."""

    FEATURE_NAMES: List[str] = [
        "ms_prev_swing_high",
        "ms_prev_swing_low",
        "ms_dist_to_prev_swing_high",
        "ms_dist_to_prev_swing_low",
        "ms_swing_range",
        "ms_swing_range_position",
        "ms_swing_age_high",
        "ms_swing_age_low",
        "ms_buy_side_sweep",
        "ms_sell_side_sweep",
        "ms_close_back_inside_range",
        "ms_bull_fvg_size_atr",
        "ms_bear_fvg_size_atr",
        "ms_upper_wick_atr",
        "ms_lower_wick_atr",
    ]

    def __init__(self, swing_window: int = 5) -> None:
        self._swing_window = swing_window

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        close = pd.to_numeric(out["close"], errors="coerce")
        high = pd.to_numeric(out["high"], errors="coerce")
        low = pd.to_numeric(out["low"], errors="coerce")
        open_ = pd.to_numeric(out["open"], errors="coerce")
        atr = self._resolve_atr(out, close)

        prev_swing_high = self._confirmed_swing(high, is_high=True)
        prev_swing_low = self._confirmed_swing(low, is_high=False)

        out["ms_prev_swing_high"] = prev_swing_high
        out["ms_prev_swing_low"] = prev_swing_low
        out["ms_dist_to_prev_swing_high"] = prev_swing_high - close
        out["ms_dist_to_prev_swing_low"] = close - prev_swing_low

        swing_range = (prev_swing_high - prev_swing_low).clip(lower=0.0)
        out["ms_swing_range"] = swing_range
        out["ms_swing_range_position"] = (
            (close - prev_swing_low) / swing_range.replace(0.0, np.nan)
        ).clip(0.0, 1.0)

        out["ms_swing_age_high"] = self._bars_since(
            prev_swing_high.ne(prev_swing_high.shift(1))
        )
        out["ms_swing_age_low"] = self._bars_since(
            prev_swing_low.ne(prev_swing_low.shift(1))
        )

        raw_buy_sweep = (high > prev_swing_high) & (close < prev_swing_high)
        raw_sell_sweep = (low < prev_swing_low) & (close > prev_swing_low)
        out["ms_buy_side_sweep"] = raw_buy_sweep.shift(1, fill_value=False).astype(int)
        out["ms_sell_side_sweep"] = raw_sell_sweep.shift(1, fill_value=False).astype(int)

        inside_range = (close <= prev_swing_high) & (close >= prev_swing_low)
        out["ms_close_back_inside_range"] = (
            inside_range & (raw_buy_sweep | raw_sell_sweep).shift(1, fill_value=False)
        ).astype(int)

        bullish_gap = (low - high.shift(2)).clip(lower=0.0)
        bearish_gap = (low.shift(2) - high).clip(lower=0.0)
        out["ms_bull_fvg_size_atr"] = (bullish_gap / atr).shift(1)
        out["ms_bear_fvg_size_atr"] = (bearish_gap / atr).shift(1)

        out["ms_upper_wick_atr"] = (high - np.maximum(open_, close)) / atr
        out["ms_lower_wick_atr"] = (np.minimum(open_, close) - low) / atr

        out = cleanup_dataframe_features(out, self.FEATURE_NAMES)
        logger.debug(
            "Market-structure/liquidity specialist features calculated: %d columns",
            len(self.FEATURE_NAMES),
        )
        return out

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()

    def _confirmed_swing(self, series: pd.Series, *, is_high: bool) -> pd.Series:
        window = self._swing_window
        if is_high:
            rolling = series.rolling(window=2 * window + 1, center=True).max()
            fallback = series.expanding(min_periods=1).max()
        else:
            rolling = series.rolling(window=2 * window + 1, center=True).min()
            fallback = series.expanding(min_periods=1).min()

        pivots = series.where(series == rolling)
        confirmed = pivots.shift(window).ffill()
        return confirmed.ffill().fillna(fallback)

    def _bars_since(self, changed: pd.Series) -> pd.Series:
        values = changed.fillna(False).to_numpy()
        age = np.zeros(len(values), dtype=float)
        last_change: int | None = None
        for idx, flag in enumerate(values):
            if flag:
                last_change = idx
                age[idx] = 0.0
            elif last_change is None:
                age[idx] = float(idx + 1)
            else:
                age[idx] = float(idx - last_change)
        return pd.Series(age, index=changed.index, dtype=float)

    def _resolve_atr(self, df: pd.DataFrame, close: pd.Series) -> pd.Series:
        if "atr_14" in df.columns:
            atr = pd.to_numeric(df["atr_14"], errors="coerce")
        else:
            atr = close.diff().abs().rolling(window=14, min_periods=1).mean()
        return atr.replace(0.0, np.nan).ffill().fillna(1.0)
