"""Dow Theory trend-confirmation package (Phase 14.1).

Classifies the prevailing trend from swing high/low structure (HH/HL vs LH/LL),
checks volume/order-flow and multi-timeframe confirmation, and produces a verdict
that confirms or contradicts the Elliott Wave master count. Pure structural logic;
the ML feature wiring lives in ``ai_engine.features.dow_theory_features``.
"""

from ai_engine.dow_theory.trend import (
    DowTrend,
    classify_primary_trend,
    confirm_with_ew,
    mtf_confirms,
    volume_confirms,
)

__all__ = [
    "DowTrend",
    "classify_primary_trend",
    "confirm_with_ew",
    "mtf_confirms",
    "volume_confirms",
]
