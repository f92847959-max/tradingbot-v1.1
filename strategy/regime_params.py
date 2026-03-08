"""Per-regime strategy parameter tables.

Maps each MarketRegime to strategy parameters (ATR multipliers,
confidence thresholds, score minimums) so the strategy can adapt
its behavior to current market conditions.

Values are conservative defaults from TA literature; Phase 5
backtesting will validate and potentially tune them.
"""

from strategy.regime_detector import MarketRegime

# Per-regime strategy parameters
REGIME_PARAMS: dict[MarketRegime, dict] = {
    MarketRegime.TRENDING: {
        "tp_atr_multiplier": 2.5,  # Let winners run in trends
        "sl_atr_multiplier": 1.5,  # Standard SL
        "min_confidence": 0.65,  # Slightly lower bar
        "min_trade_score": 55,  # More willing to trade
        "rr_min": 1.5,  # Standard R:R
    },
    MarketRegime.RANGING: {
        "tp_atr_multiplier": 1.5,  # Tighter TP (mean reversion)
        "sl_atr_multiplier": 1.0,  # Tighter SL
        "min_confidence": 0.75,  # Higher bar
        "min_trade_score": 65,  # More selective
        "rr_min": 1.2,  # Accept lower R:R
    },
    MarketRegime.VOLATILE: {
        "tp_atr_multiplier": 3.0,  # Wide TP (big moves possible)
        "sl_atr_multiplier": 2.0,  # Wide SL (avoid noise stops)
        "min_confidence": 0.80,  # Very high bar
        "min_trade_score": 70,  # Very selective
        "rr_min": 1.5,  # Standard R:R
    },
}


def get_regime_params(regime: MarketRegime) -> dict:
    """Return parameter dict for the given regime.

    Falls back to RANGING params if regime not found (safest default).
    """
    return REGIME_PARAMS.get(regime, REGIME_PARAMS[MarketRegime.RANGING])
