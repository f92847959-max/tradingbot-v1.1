"""Market regime detector using ADX and ATR ratio.

Classifies market state into TRENDING, RANGING, or VOLATILE to allow
strategy parameters (TP/SL multipliers, confidence thresholds) to adapt
to current conditions.
"""

import enum
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from shared.constants import (
    ADX_RANGE_THRESHOLD,
    ADX_TREND_THRESHOLD,
    ATR_VOLATILE_RATIO,
    REGIME_LOOKBACK_PERIODS,
    REGIME_MIN_CONFIRM_CANDLES,
)

logger = logging.getLogger(__name__)


class MarketRegime(enum.Enum):
    TRENDING = "trending"
    RANGING = "ranging"
    VOLATILE = "volatile"


@dataclass
class RegimeState:
    """Current regime classification with supporting data."""

    regime: MarketRegime
    adx: float
    atr: float
    atr_ratio: float  # atr / atr_average
    confidence: float  # 0-1 how clearly this regime is classified


class RegimeDetector:
    """Rule-based market regime classifier using ADX, ATR ratio, and BB width.

    Classification priority (checked in order):
    1. VOLATILE: ATR > atr_volatile_ratio * rolling_avg_ATR
    2. TRENDING: ADX > adx_trend_threshold
    3. RANGING:  ADX < adx_range_threshold
    4. Ambiguous zone (adx_range <= ADX <= adx_trend): tiebreak by ATR ratio

    Hysteresis: Requires ``min_confirm_candles`` consecutive candles of same
    regime before switching (prevents flickering).
    """

    def __init__(
        self,
        adx_trend_threshold: float = ADX_TREND_THRESHOLD,
        adx_range_threshold: float = ADX_RANGE_THRESHOLD,
        atr_volatile_ratio: float = ATR_VOLATILE_RATIO,
        lookback_periods: int = REGIME_LOOKBACK_PERIODS,
        min_confirm_candles: int = REGIME_MIN_CONFIRM_CANDLES,
    ) -> None:
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold
        self.atr_volatile_ratio = atr_volatile_ratio
        self.lookback_periods = lookback_periods
        self.min_confirm_candles = min_confirm_candles

        # Hysteresis state for live trading (detect method)
        self._current_regime: Optional[MarketRegime] = None
        self._pending_regime: Optional[MarketRegime] = None
        self._confirm_count: int = 0

    def detect(self, df: pd.DataFrame) -> RegimeState:
        """Classify current market regime from latest indicator values.

        Reads from columns: adx (or adx_14), atr_14.
        Uses last ``lookback_periods`` rows for ATR average.

        Returns RegimeState with regime enum, raw values, and confidence.
        """
        if df.empty:
            logger.warning("Empty DataFrame passed to regime detector")
            return RegimeState(
                regime=MarketRegime.RANGING,
                adx=0.0,
                atr=0.0,
                atr_ratio=0.0,
                confidence=0.0,
            )

        last = df.iloc[-1]

        # ADX column lookup: try 'adx' first, then 'adx_14'
        adx_val = last.get("adx", last.get("adx_14"))
        if adx_val is None or pd.isna(adx_val):
            logger.debug("ADX is missing or NaN, defaulting to 0.0")
            adx_val = 0.0

        # ATR
        atr_val = last.get("atr_14", last.get("atr"))
        if atr_val is None or pd.isna(atr_val):
            logger.debug("ATR is missing or NaN, defaulting to RANGING with confidence 0")
            return RegimeState(
                regime=MarketRegime.RANGING,
                adx=float(adx_val),
                atr=0.0,
                atr_ratio=0.0,
                confidence=0.0,
            )

        atr_val = float(atr_val)
        adx_val = float(adx_val)

        # Compute rolling ATR average for ratio
        lookback = min(self.lookback_periods, len(df))
        atr_col_name = "atr_14" if "atr_14" in df.columns else "atr"
        if atr_col_name not in df.columns:
             atr_avg = atr_val if atr_val > 0 else 1.0
        else:
            atr_col = df[atr_col_name].iloc[-lookback:]
            atr_avg = atr_col.mean()
            if pd.isna(atr_avg) or atr_avg == 0:
                atr_avg = atr_val if atr_val > 0 else 1.0

        atr_ratio = atr_val / atr_avg

        # Core classification
        raw_regime, confidence = self._classify_single(adx_val, atr_val, atr_avg)

        # Apply hysteresis
        regime = self._apply_hysteresis(raw_regime)

        return RegimeState(
            regime=regime,
            adx=adx_val,
            atr=atr_val,
            atr_ratio=atr_ratio,
            confidence=confidence,
        )

    def detect_series(self, df: pd.DataFrame) -> pd.Series:
        """Classify regime for every row in the DataFrame.

        Returns pd.Series of MarketRegime values, same index as df.
        Uses vectorized logic (no hysteresis -- for training/backtesting).
        """
        if df.empty:
            return pd.Series(dtype=object)

        # Resolve ADX column
        if "adx" in df.columns:
            adx_series = df["adx"]
        elif "adx_14" in df.columns:
            adx_series = df["adx_14"]
        else:
            adx_series = pd.Series(0.0, index=df.index)

        # ATR column
        if "atr_14" not in df.columns:
            return pd.Series(
                MarketRegime.RANGING, index=df.index, dtype=object
            )

        atr_series = df["atr_14"]
        # Use the full lookback window to avoid look-ahead / under-filled
        # windows biasing early rows. Rows where the window is not yet
        # fully formed will be NaN and fall through to the RANGING default.
        atr_avg = atr_series.rolling(
            window=self.lookback_periods,
            min_periods=self.lookback_periods,
        ).mean()

        # Avoid division by zero
        safe_avg = atr_avg.replace(0, np.nan).fillna(1.0)
        atr_ratio = atr_series / safe_avg

        # Vectorized classification (priority order)
        regimes = pd.Series(MarketRegime.RANGING, index=df.index, dtype=object)

        # Priority 3: RANGING is default (already set)

        # Priority 2: TRENDING where ADX > threshold
        trending_mask = adx_series > self.adx_trend_threshold
        regimes[trending_mask] = MarketRegime.TRENDING

        # Ambiguous zone tiebreak: adx_range <= ADX <= adx_trend
        ambiguous_mask = (
            (adx_series >= self.adx_range_threshold)
            & (adx_series <= self.adx_trend_threshold)
        )
        # In ambiguous zone, high ATR ratio tips toward TRENDING
        ambiguous_trending = ambiguous_mask & (atr_ratio > 1.2)
        regimes[ambiguous_trending] = MarketRegime.TRENDING

        # Priority 1 (highest): VOLATILE overrides everything
        volatile_mask = atr_ratio > self.atr_volatile_ratio
        regimes[volatile_mask] = MarketRegime.VOLATILE

        # NaN handling: where ATR is NaN, set RANGING
        nan_mask = atr_series.isna()
        regimes[nan_mask] = MarketRegime.RANGING

        return regimes

    def _classify_single(
        self, adx: float, atr: float, atr_avg: float
    ) -> tuple[MarketRegime, float]:
        """Core classification logic for a single observation.

        Returns (regime, confidence) tuple. Confidence:
        - 1.0 when clearly in regime (ADX > 35 for trending, etc.)
        - 0.5-0.8 when near thresholds
        """
        # Avoid division by zero
        if atr_avg == 0:
            atr_avg = 1.0
        atr_ratio = atr / atr_avg

        # Priority 1: VOLATILE (ATR spike)
        if atr_ratio > self.atr_volatile_ratio:
            # Confidence scales with how far above threshold
            excess = atr_ratio - self.atr_volatile_ratio
            confidence = min(1.0, 0.6 + excess * 0.4)
            return MarketRegime.VOLATILE, confidence

        # Priority 2: TRENDING (high ADX)
        if adx > self.adx_trend_threshold:
            # Confidence: 0.6 at threshold, 1.0 at threshold+15
            excess = adx - self.adx_trend_threshold
            confidence = min(1.0, 0.6 + excess / 15.0 * 0.4)
            return MarketRegime.TRENDING, confidence

        # Priority 3: RANGING (low ADX)
        if adx < self.adx_range_threshold:
            # Confidence: 0.6 at threshold, 1.0 at threshold-10
            deficit = self.adx_range_threshold - adx
            confidence = min(1.0, 0.6 + deficit / 10.0 * 0.4)
            return MarketRegime.RANGING, confidence

        # Ambiguous zone: adx_range <= adx <= adx_trend
        # Tiebreak by ATR ratio
        if atr_ratio > 1.2:
            return MarketRegime.TRENDING, 0.5
        else:
            return MarketRegime.RANGING, 0.5

    def _apply_hysteresis(self, raw_regime: MarketRegime) -> MarketRegime:
        """Apply hysteresis to prevent regime flickering.

        Only switches regime after ``min_confirm_candles`` consecutive
        detections of the new regime. The counter tracks how many
        consecutive candles have reported the *candidate* new regime.
        """
        if self._current_regime is None:
            # First detection — accept immediately
            self._current_regime = raw_regime
            self._pending_regime = None
            self._confirm_count = 0
            return raw_regime

        if raw_regime == self._current_regime:
            # Raw matches current regime -> any pending switch is aborted.
            # Do NOT touch current regime, just clear the pending counter.
            self._pending_regime = None
            self._confirm_count = 0
            return self._current_regime

        # Different regime detected -> this is a candidate switch
        if getattr(self, "_pending_regime", None) != raw_regime:
            # New candidate regime -> start counting from 1
            self._pending_regime = raw_regime
            self._confirm_count = 1
        else:
            # Same candidate as before -> increment streak
            self._confirm_count += 1

        if self._confirm_count >= self.min_confirm_candles:
            # Confirmed switch
            logger.info(
                "Regime switch: %s -> %s (after %d confirmations)",
                self._current_regime.value,
                raw_regime.value,
                self._confirm_count,
            )
            self._current_regime = raw_regime
            self._pending_regime = None
            self._confirm_count = 0
            return raw_regime

        # Not yet confirmed — stick with current regime
        return self._current_regime
