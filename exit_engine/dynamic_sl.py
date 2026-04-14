"""Dynamic stop-loss calculator using ATR and market structure levels.

Replaces fixed ATR-based SL with regime-aware calculation that also
incorporates nearest support/resistance structure when available.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from exit_engine.types import StructureLevel
from strategy.regime_detector import MarketRegime
from strategy.regime_params import get_regime_params
from shared.constants import PIP_SIZE

logger = logging.getLogger(__name__)


def calculate_dynamic_sl(
    direction: str,
    entry_price: float,
    atr: float,
    regime: MarketRegime,
    structure_levels: list[StructureLevel] | None = None,
    pip_size: float = PIP_SIZE,
    min_sl_pips: float = 5.0,
    structure_buffer_pips: float = 2.0,
) -> tuple[float, str]:
    """Calculate a regime-aware ATR-based stop loss with optional structure adjustment.

    Args:
        direction: "BUY" or "SELL"
        entry_price: Trade entry price
        atr: Current ATR-14 value (must be > 0)
        regime: Current MarketRegime classification
        structure_levels: Optional list of support/resistance levels
        pip_size: Pip size for the instrument (default 0.01 for Gold)
        min_sl_pips: Minimum SL distance in pips
        structure_buffer_pips: Buffer pips beyond the structure level

    Returns:
        (stop_loss_price, reason) where reason is "atr", "structure", or "atr+structure"

    Raises:
        ValueError: If ATR is None, zero, or negative
    """
    if atr is None or atr <= 0:
        raise ValueError(f"ATR must be positive, got: {atr}")

    params = get_regime_params(regime)
    sl_atr_multiplier = params["sl_atr_multiplier"]
    atr_sl_distance = atr * sl_atr_multiplier

    min_distance = min_sl_pips * pip_size
    buffer = structure_buffer_pips * pip_size

    if direction == "BUY":
        atr_sl = entry_price - atr_sl_distance
        reason = "atr"

        if structure_levels:
            supports = [s for s in structure_levels if s.level_type == "support" and s.price < entry_price]
            if supports:
                nearest_support = max(supports, key=lambda s: s.price)
                structure_sl = nearest_support.price - buffer
                sl = max(atr_sl, structure_sl)
                reason = "atr+structure" if sl != atr_sl else "atr"
            else:
                sl = atr_sl
        else:
            sl = atr_sl

        # Apply minimum floor
        if entry_price - sl < min_distance:
            sl = entry_price - min_distance

    else:  # SELL
        atr_sl = entry_price + atr_sl_distance
        reason = "atr"

        if structure_levels:
            resistances = [s for s in structure_levels if s.level_type == "resistance" and s.price > entry_price]
            if resistances:
                nearest_resistance = min(resistances, key=lambda s: s.price)
                structure_sl = nearest_resistance.price + buffer
                sl = min(atr_sl, structure_sl)
                reason = "atr+structure" if sl != atr_sl else "atr"
            else:
                sl = atr_sl
        else:
            sl = atr_sl

        # Apply minimum floor
        if sl - entry_price < min_distance:
            sl = entry_price + min_distance

    return round(sl, 2), reason


def find_swing_levels(
    df: pd.DataFrame,
    lookback: int = 20,
    min_touches: int = 2,
    atr: float | None = None,
) -> list[StructureLevel]:
    """Detect swing high/low structure levels from recent candles.

    Args:
        df: OHLC DataFrame with 'high' and 'low' columns
        lookback: Number of candles to scan
        min_touches: Minimum number of touches to qualify as a level
        atr: Current ATR for grouping nearby levels (default: 0.5% of avg price)

    Returns:
        List of StructureLevel objects with strength >= min_touches
    """
    if len(df) < 3:
        return []

    data = df.tail(lookback).copy()
    highs = data["high"].values
    lows = data["low"].values

    if atr is None or atr <= 0:
        atr = float(np.mean(highs)) * 0.005  # fallback: 0.5% of price

    cluster_distance = atr * 0.5

    # Detect swing highs: high[i] > high[i-1] and high[i] > high[i+1]
    swing_high_prices = []
    for i in range(1, len(highs) - 1):
        if highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
            swing_high_prices.append(highs[i])

    # Detect swing lows: low[i] < low[i-1] and low[i] < low[i+1]
    swing_low_prices = []
    for i in range(1, len(lows) - 1):
        if lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
            swing_low_prices.append(lows[i])

    def cluster_levels(prices: list[float], level_type: str, source: str) -> list[StructureLevel]:
        if not prices:
            return []
        sorted_prices = sorted(prices)
        clusters: list[list[float]] = []
        current_cluster = [sorted_prices[0]]
        for p in sorted_prices[1:]:
            if p - current_cluster[0] <= cluster_distance:
                current_cluster.append(p)
            else:
                clusters.append(current_cluster)
                current_cluster = [p]
        clusters.append(current_cluster)

        levels = []
        for cluster in clusters:
            if len(cluster) >= min_touches:
                levels.append(StructureLevel(
                    price=round(float(np.mean(cluster)), 2),
                    level_type=level_type,
                    strength=len(cluster),
                    source=source,
                ))
        return levels

    result = []
    result.extend(cluster_levels(swing_high_prices, "resistance", "swing_high"))
    result.extend(cluster_levels(swing_low_prices, "support", "swing_low"))
    return result
