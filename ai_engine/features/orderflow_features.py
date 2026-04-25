"""OHLCV-derived order-flow features.

Capital.com does not expose true multi-level DOM for this project, so this
module builds leakage-aware order-flow approximations from closed candles plus
optional Level-1 quote enrichment columns.
"""

from __future__ import annotations

import logging
from typing import List

import numpy as np
import pandas as pd

from shared.utils import cleanup_dataframe_features

logger = logging.getLogger(__name__)


class OrderFlowFeatures:
    """Build robust `flow_*` features for training and live inference."""

    FEATURE_NAMES: List[str] = [
        "flow_delta",
        "flow_delta_cumulative_20",
        "flow_delta_divergence",
        "flow_buy_pressure",
        "flow_poc_distance",
        "flow_vah_distance",
        "flow_val_distance",
        "flow_liq_zone_above",
        "flow_liq_zone_below",
        "flow_fvg_above",
        "flow_fvg_below",
        "flow_absorption_score",
        "flow_volume_zscore",
        "flow_l1_imbalance",
        "flow_l1_imbalance_ema_10",
    ]

    def __init__(
        self,
        profile_window: int = 200,
        profile_bins: int = 40,
        liquidity_window: int = 20,
        absorption_window: int = 20,
    ) -> None:
        self.profile_window = max(20, int(profile_window))
        self.profile_bins = max(10, int(profile_bins))
        self.liquidity_window = max(5, int(liquidity_window))
        self.absorption_window = max(5, int(absorption_window))

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add OHLCV-derived order-flow features to a DataFrame."""
        out = df.copy()

        open_ = _series_or_default(out, "open", 0.0)
        high = _series_or_default(out, "high", 0.0)
        low = _series_or_default(out, "low", 0.0)
        close = _series_or_default(out, "close", 0.0)
        volume = _series_or_default(out, "volume", 0.0).clip(lower=0.0)
        atr = self._resolve_atr(out, high, low, close)

        delta, buy_pressure = self._compute_delta(open_, high, low, close, volume)
        out["flow_delta"] = delta
        out["flow_buy_pressure"] = buy_pressure
        out["flow_delta_cumulative_20"] = delta.rolling(window=20, min_periods=1).sum()
        out["flow_delta_divergence"] = self._compute_delta_divergence(close, out["flow_delta_cumulative_20"])

        poc, vah, val = self._rolling_volume_profile(high, low, close, volume)
        out["flow_poc_distance"] = _normalised_distance(poc, close, atr)
        out["flow_vah_distance"] = _normalised_distance(vah, close, atr)
        out["flow_val_distance"] = _normalised_distance(val, close, atr)

        out["flow_liq_zone_above"] = self._liquidity_zone_distance(high, close, atr, above=True)
        out["flow_liq_zone_below"] = self._liquidity_zone_distance(low, close, atr, above=False)

        fvg_above, fvg_below = self._closed_candle_fvg_distances(high, low, close, atr)
        out["flow_fvg_above"] = fvg_above
        out["flow_fvg_below"] = fvg_below

        out["flow_absorption_score"] = self._absorption_score(open_, close, volume)
        out["flow_volume_zscore"] = _rolling_zscore(volume, window=self.absorption_window).clip(-5.0, 5.0)

        l1_imbalance = _series_or_default(out, "flow_l1_imbalance", 0.0).clip(-1.0, 1.0)
        out["flow_l1_imbalance"] = l1_imbalance
        out["flow_l1_imbalance_ema_10"] = l1_imbalance.ewm(span=10, adjust=False).mean()

        out = cleanup_dataframe_features(out, self.FEATURE_NAMES)
        logger.debug("Order-flow features calculated: %d columns", len(self.FEATURE_NAMES))
        return out

    def get_feature_names(self) -> List[str]:
        return self.FEATURE_NAMES.copy()

    def _compute_delta(
        self,
        open_: pd.Series,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        price_range = (high - low).abs().clip(lower=1e-6)
        direction = ((close - open_) / price_range).clip(-1.0, 1.0)
        delta = volume * direction
        buy_pressure = (delta / volume.clip(lower=1.0)).clip(-1.0, 1.0)
        return delta, buy_pressure

    def _compute_delta_divergence(self, close: pd.Series, cumulative_delta: pd.Series) -> pd.Series:
        price_change = close.diff(14)
        delta_change = cumulative_delta.diff(14)
        divergence = np.sign(delta_change) - np.sign(price_change)
        return pd.Series(divergence, index=close.index, dtype=float).clip(-2.0, 2.0)

    def _rolling_volume_profile(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        n = len(close)
        poc = np.full(n, np.nan, dtype=float)
        vah = np.full(n, np.nan, dtype=float)
        val = np.full(n, np.nan, dtype=float)
        min_periods = max(20, self.profile_window // 10)

        high_arr = high.to_numpy(dtype=float)
        low_arr = low.to_numpy(dtype=float)
        volume_arr = volume.to_numpy(dtype=float)

        for idx in range(n):
            start = max(0, idx - self.profile_window + 1)
            if idx - start + 1 < min_periods:
                continue
            poc[idx], vah[idx], val[idx] = _volume_profile_levels(
                high_arr[start : idx + 1],
                low_arr[start : idx + 1],
                volume_arr[start : idx + 1],
                self.profile_bins,
            )

        return (
            pd.Series(poc, index=close.index),
            pd.Series(vah, index=close.index),
            pd.Series(val, index=close.index),
        )

    def _liquidity_zone_distance(
        self,
        price: pd.Series,
        close: pd.Series,
        atr: pd.Series,
        *,
        above: bool,
    ) -> pd.Series:
        shifted_price = price.shift(1)
        if above:
            zone = shifted_price.rolling(window=self.liquidity_window, min_periods=3).max()
            distance = (zone - close).clip(lower=0.0)
        else:
            zone = shifted_price.rolling(window=self.liquidity_window, min_periods=3).min()
            distance = (close - zone).clip(lower=0.0)
        return distance / atr.clip(lower=1e-6)

    def _closed_candle_fvg_distances(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        atr: pd.Series,
    ) -> tuple[pd.Series, pd.Series]:
        bullish_gap_mid = ((low + high.shift(2)) / 2.0).where(low > high.shift(2)).shift(1)
        bearish_gap_mid = ((high + low.shift(2)) / 2.0).where(high < low.shift(2)).shift(1)

        bull_level = bullish_gap_mid.ffill()
        bear_level = bearish_gap_mid.ffill()

        below = (close - bull_level).clip(lower=0.0) / atr.clip(lower=1e-6)
        above = (bear_level - close).clip(lower=0.0) / atr.clip(lower=1e-6)
        return above, below

    def _absorption_score(self, open_: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        body = (close - open_).abs().clip(lower=1e-4)
        volume_body_ratio = volume / body
        score = _rolling_zscore(volume_body_ratio, window=self.absorption_window)
        return score.clip(-5.0, 5.0)

    def _resolve_atr(
        self,
        df: pd.DataFrame,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.Series:
        if "atr_14" in df.columns:
            atr = pd.to_numeric(df["atr_14"], errors="coerce")
        else:
            prev_close = close.shift(1).fillna(close)
            true_range = pd.concat(
                [
                    (high - low).abs(),
                    (high - prev_close).abs(),
                    (low - prev_close).abs(),
                ],
                axis=1,
            ).max(axis=1)
            atr = true_range.rolling(window=14, min_periods=1).mean()
        return atr.replace(0.0, np.nan).ffill().fillna(1.0)


def _series_or_default(df: pd.DataFrame, column: str, default: float) -> pd.Series:
    if column in df.columns:
        series = pd.to_numeric(df[column], errors="coerce")
    else:
        series = pd.Series(default, index=df.index, dtype=float)
    return series.fillna(default)


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    mean = series.rolling(window=window, min_periods=max(3, window // 4)).mean()
    std = series.rolling(window=window, min_periods=max(3, window // 4)).std()
    safe_std = std.replace(0.0, np.nan)
    return (series - mean) / safe_std


def _normalised_distance(level: pd.Series, close: pd.Series, atr: pd.Series) -> pd.Series:
    return (level - close) / atr.clip(lower=1e-6)


def _volume_profile_levels(
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray,
    bins_count: int,
) -> tuple[float, float, float]:
    price_min = float(np.nanmin(low))
    price_max = float(np.nanmax(high))
    if not np.isfinite(price_min) or not np.isfinite(price_max) or price_max <= price_min:
        mid = (price_min + price_max) / 2.0 if np.isfinite(price_min + price_max) else 0.0
        return mid, mid, mid

    bins = np.linspace(price_min, price_max, bins_count + 1)
    profile = np.zeros(bins_count, dtype=float)

    for candle_high, candle_low, candle_volume in zip(high, low, volume):
        if not np.isfinite(candle_high + candle_low + candle_volume) or candle_volume <= 0.0:
            continue
        lo_idx = int(np.searchsorted(bins, candle_low, side="right") - 1)
        hi_idx = int(np.searchsorted(bins, candle_high, side="left"))
        lo_idx = max(0, min(lo_idx, bins_count - 1))
        hi_idx = max(lo_idx + 1, min(hi_idx + 1, bins_count))
        profile[lo_idx:hi_idx] += candle_volume / max(hi_idx - lo_idx, 1)

    if profile.sum() <= 0.0:
        mid = (price_min + price_max) / 2.0
        return mid, mid, mid

    poc_idx = int(np.argmax(profile))
    poc = float((bins[poc_idx] + bins[poc_idx + 1]) / 2.0)

    sorted_idx = np.argsort(profile)[::-1]
    cumulative = 0.0
    selected: list[int] = []
    target = profile.sum() * 0.70
    for idx in sorted_idx:
        cumulative += profile[idx]
        selected.append(int(idx))
        if cumulative >= target:
            break

    val_idx = min(selected)
    vah_idx = max(selected)
    val = float((bins[val_idx] + bins[val_idx + 1]) / 2.0)
    vah = float((bins[vah_idx] + bins[vah_idx + 1]) / 2.0)
    return poc, vah, val
