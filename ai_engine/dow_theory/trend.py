"""Dow Theory trend classification (Phase 14.1).

Pure, never-raising structural logic. ``classify_primary_trend`` reads the
alternating peaks/valleys produced by ``WaveDetector.detect_swings`` and applies
Dow's higher-high/higher-low (uptrend) vs lower-high/lower-low (downtrend) rule.
The remaining helpers express EW agreement, volume/order-flow confirmation, and
multi-timeframe confirmation. None of these raise — on bad input they return the
neutral / unconfirmed result so the feature pipeline can never crash.
"""

from __future__ import annotations

import logging
from enum import IntEnum

logger = logging.getLogger(__name__)

# Minimum confirmed pivots per side (peaks AND valleys) for a directional read.
_MIN_PIVOTS_PER_SIDE = 2
# Recent vs baseline window for the volume/flow participation heuristic.
_VOL_RECENT = 3


class DowTrend(IntEnum):
    """Primary trend direction. Int values double as the ML feature encoding."""

    DOWN = 0
    RANGE = 1
    UP = 2


def _split_peaks_valleys(swings):
    """Split WavePoints into (peaks, valleys), preserving chronological order."""
    peaks, valleys = [], []
    for p in swings or []:
        et = getattr(p, "extremum_type", None)
        et = getattr(et, "value", et)  # ExtremumType -> "peak"/"valley"
        if et == "peak":
            peaks.append(p)
        elif et == "valley":
            valleys.append(p)
    return peaks, valleys


def classify_primary_trend(swings) -> DowTrend:
    """Classify the primary trend from swing high/low structure.

    UP when the last two peaks are rising (HH) AND the last two valleys are
    rising (HL); DOWN when the last two peaks fall (LH) AND valleys fall (LL);
    RANGE otherwise or on insufficient data. Never raises.
    """
    try:
        peaks, valleys = _split_peaks_valleys(swings)
        if len(peaks) < _MIN_PIVOTS_PER_SIDE or len(valleys) < _MIN_PIVOTS_PER_SIDE:
            return DowTrend.RANGE
        higher_high = peaks[-1].price > peaks[-2].price
        higher_low = valleys[-1].price > valleys[-2].price
        lower_high = peaks[-1].price < peaks[-2].price
        lower_low = valleys[-1].price < valleys[-2].price
        if higher_high and higher_low:
            return DowTrend.UP
        if lower_high and lower_low:
            return DowTrend.DOWN
        return DowTrend.RANGE
    except Exception:
        return DowTrend.RANGE


def confirm_with_ew(dow_trend: DowTrend, ew_direction: int) -> int:
    """Agreement between the Dow primary trend and the EW directional bias.

    Returns +1 when Dow confirms EW (same direction), -1 when it contradicts,
    and 0 when either side has no directional read. ``ew_direction`` is the
    Elliott Wave primary count's direction (+1 bullish / -1 bearish / 0 unknown).
    """
    try:
        if dow_trend == DowTrend.RANGE:
            return 0
        ew = int(ew_direction or 0)
        ew = 1 if ew > 0 else (-1 if ew < 0 else 0)
        if ew == 0:
            return 0
        dow_dir = 1 if dow_trend == DowTrend.UP else -1
        return 1 if dow_dir == ew else -1
    except Exception:
        return 0


def volume_confirms(df, dow_trend: DowTrend) -> bool:
    """True when volume / order-flow supports the (directional) trend.

    Dow Theory holds that volume should expand in the direction of the primary
    trend. Without signed volume we use a participation proxy: recent average
    volume/flow exceeding the prior baseline. Prefers Phase-13 ``flow_*`` columns,
    falls back to ``volume``; returns False (unknown) when neither exists, on a
    RANGE trend, or on any error.
    """
    try:
        if dow_trend == DowTrend.RANGE or df is None or len(df) <= _VOL_RECENT:
            return False
        col = None
        if "volume" in df.columns:
            col = "volume"
        else:
            flow_cols = [c for c in df.columns if str(c).startswith("flow_")]
            col = flow_cols[0] if flow_cols else None
        if col is None:
            return False
        series = df[col].astype(float)
        recent = float(series.iloc[-_VOL_RECENT:].mean())
        baseline = float(series.iloc[:-_VOL_RECENT].mean())
        if recent != recent or baseline != baseline:  # NaN guard
            return False
        return recent >= baseline
    except Exception:
        return False


def mtf_confirms(primary_trend: DowTrend, higher_tf_trend: DowTrend) -> bool:
    """True when the higher timeframe's trend agrees with the primary timeframe.

    Dow's "two averages must confirm" analogue: both timeframes must show the
    same directional trend (a RANGE on either side is not a confirmation).
    """
    try:
        if primary_trend == DowTrend.RANGE or higher_tf_trend == DowTrend.RANGE:
            return False
        return primary_trend == higher_tf_trend
    except Exception:
        return False
