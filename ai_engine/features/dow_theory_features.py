"""Dow Theory ML feature group (Phase 14.1).

Extracts 4 causal Dow Theory features from an OHLCV DataFrame and appends them as
new columns. Mirrors ``elliott_wave_features``: features are computed once on the
(capped) incoming window and broadcast to every row — no lookahead across rows.

Features
--------
dow_trend : int            0 = DOWN, 1 = RANGE, 2 = UP  (``DowTrend`` encoding)
dow_confirms_ew : int      1 when the Dow trend confirms the Elliott Wave primary
                           count's direction, else 0
dow_volume_confirmed : int 1 when volume / order-flow supports the trend, else 0
dow_mtf_confirmed : int    1 when a higher timeframe agrees with the trend, else 0

The neutral default for ``dow_trend`` is RANGE (1), never DOWN (0), so missing
data does not masquerade as a bearish read.

Threat mitigation
-----------------
T-14.1-01 (DoS): detector input is capped at ``DOW_MAX_WINDOW`` rows
(Windows-safe; mirrors ``elliott_wave_features.EW_MAX_WINDOW``).
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from ai_engine.dow_theory.trend import (
    DowTrend,
    classify_primary_trend,
    confirm_with_ew,
    mtf_confirms,
    volume_confirms,
)
from ai_engine.elliott_wave.detector import WaveDetector
from ai_engine.elliott_wave.rules import RuleEngine
from ai_engine.elliott_wave.scoring import get_primary_count

logger = logging.getLogger(__name__)

# Hard cap on the candle window fed to the detector (T-14.1-01).
DOW_MAX_WINDOW: int = 300
# Coarse higher-timeframe proxy stride when no explicit MTF frame is supplied.
_HTF_STRIDE: int = 3

FEATURE_NAMES: List[str] = [
    "dow_trend",
    "dow_confirms_ew",
    "dow_volume_confirmed",
    "dow_mtf_confirmed",
]


def _zero_features() -> dict:
    """Neutral defaults: RANGE trend, nothing confirmed."""
    return {
        "dow_trend": int(DowTrend.RANGE.value),
        "dow_confirms_ew": 0,
        "dow_volume_confirmed": 0,
        "dow_mtf_confirmed": 0,
    }


def _swing_trend(df, price_column: str = "close") -> DowTrend:
    """Classify the Dow trend from a price frame's swings. Never raises."""
    try:
        cols = getattr(df, "columns", [])
        if df is None or len(df) < 6 or price_column not in cols:
            return DowTrend.RANGE
        swings = WaveDetector().detect_swings(df, price_column=price_column)
        return classify_primary_trend(swings)
    except Exception:
        return DowTrend.RANGE


def _ew_direction(swings) -> int:
    """Direction (+1/-1/0) of the Elliott Wave primary count for these swings."""
    try:
        primary = get_primary_count(RuleEngine().scan(swings))
        return int(getattr(primary, "direction", 0)) if primary else 0
    except Exception:
        return 0


def extract_dow_features(ohlcv_df, mtf: Optional[dict] = None) -> dict:
    """Run the Dow pipeline on ``ohlcv_df`` and return a feature dict.

    Uses only the last ``DOW_MAX_WINDOW`` rows (T-14.1-01). Higher-timeframe
    confirmation prefers an explicit ``mtf`` frame (dict of timeframe -> DataFrame)
    and falls back to a coarse resample of the same window. Never raises — returns
    neutral defaults on any failure.
    """
    features = _zero_features()
    cols = getattr(ohlcv_df, "columns", [])
    if ohlcv_df is None or len(ohlcv_df) == 0 or "close" not in cols:
        return features

    df_window = ohlcv_df.iloc[-DOW_MAX_WINDOW:].copy()
    df_window = df_window.dropna(subset=["close"])
    if len(df_window) < 6:
        return features

    try:
        swings = WaveDetector().detect_swings(df_window, price_column="close")
        dow_trend = classify_primary_trend(swings)
        features["dow_trend"] = int(dow_trend.value)
        features["dow_confirms_ew"] = 1 if confirm_with_ew(dow_trend, _ew_direction(swings)) == 1 else 0
        features["dow_volume_confirmed"] = int(volume_confirms(df_window, dow_trend))

        htf_trend = DowTrend.RANGE
        if isinstance(mtf, dict) and mtf:
            for tf in ("1h", "30m", "15m", "5m"):
                frame = mtf.get(tf)
                if frame is not None and len(frame) >= 6:
                    htf_trend = _swing_trend(frame)
                    break
        else:
            htf_trend = _swing_trend(df_window.iloc[::_HTF_STRIDE])
        features["dow_mtf_confirmed"] = int(mtf_confirms(dow_trend, htf_trend))
    except Exception as exc:
        logger.debug("Dow feature extraction failed (non-fatal): %s", exc)

    return features


class DowTheoryFeatures:
    """Feature group following the FeatureEngineer sub-calculator protocol."""

    def __init__(self, dow_enabled: bool = True) -> None:
        self._dow_enabled = dow_enabled

    def get_feature_names(self) -> List[str]:
        return FEATURE_NAMES.copy()

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append the 4 Dow features to ``df`` (computed once, broadcast to rows).

        When disabled, all columns are filled with neutral defaults so downstream
        code never sees missing columns.
        """
        defaults = _zero_features()
        if not self._dow_enabled:
            for name in FEATURE_NAMES:
                df[name] = defaults[name]
            return df
        feats = extract_dow_features(df)
        for name in FEATURE_NAMES:
            df[name] = feats.get(name, defaults[name])
        return df
