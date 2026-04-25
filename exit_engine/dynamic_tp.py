"""Dynamic take-profit calculator using Fibonacci extensions and S/R zones.

Replaces fixed ATR-based TP with intelligent TP aligned to actual market
structure: Fibonacci extension levels and nearest support/resistance zones.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from exit_engine.types import StructureLevel, TakeProfitResult
from strategy.regime_detector import MarketRegime
from strategy.regime_params import get_regime_params
from shared.constants import PIP_SIZE

logger = logging.getLogger(__name__)

# Standard Fibonacci extension ratios
_FIB_RATIOS = [1.0, 1.272, 1.618, 2.0, 2.618]


def fibonacci_extensions(
    entry: float,
    swing_low: float,
    swing_high: float,
) -> list[float]:
    """Calculate Fibonacci extension levels from a swing range.

    For an upswing, extensions project above swing_high.
    Levels use ratios: 1.0, 1.272, 1.618, 2.0, 2.618.

    Args:
        entry: Trade entry price (used for context, not computation)
        swing_low: Lowest price of the reference swing
        swing_high: Highest price of the reference swing

    Returns:
        Sorted list of 5 Fibonacci extension prices
    """
    swing_range = swing_high - swing_low
    # Extensions project from swing_high: base + range * (ratio - 1.0)
    levels = [swing_high + swing_range * (r - 1.0) for r in _FIB_RATIOS]
    return sorted(levels)


def find_sr_levels(
    df: pd.DataFrame,
    lookback: int = 50,
) -> list[StructureLevel]:
    """Find support (swing lows) and resistance (swing highs) from candle data.

    Uses a rolling window of 5 candles: local min in 'low' = support,
    local max in 'high' = resistance. Groups nearby levels within 0.3%
    price distance and counts touches.

    Args:
        df: OHLC DataFrame with 'high' and 'low' columns
        lookback: Number of recent candles to analyse

    Returns:
        List of StructureLevel sorted by strength descending
    """
    if len(df) < 5:
        return []

    data = df.tail(lookback).copy()
    highs = data["high"]
    lows = data["low"]

    avg_price = float(highs.mean())
    cluster_pct = 0.003  # 0.3% price distance for grouping

    # Swing highs: rolling max over window=5 with center=True
    roll_max = highs.rolling(window=5, center=True).max()
    swing_high_mask = highs == roll_max
    swing_high_prices = highs[swing_high_mask].dropna().tolist()

    # Swing lows: rolling min over window=5 with center=True
    roll_min = lows.rolling(window=5, center=True).min()
    swing_low_mask = lows == roll_min
    swing_low_prices = lows[swing_low_mask].dropna().tolist()

    def cluster_prices(prices: list[float], level_type: str, source: str) -> list[StructureLevel]:
        if not prices:
            return []
        sorted_prices = sorted(prices)
        clusters: list[list[float]] = []
        current: list[float] = [sorted_prices[0]]
        threshold = avg_price * cluster_pct
        for p in sorted_prices[1:]:
            if p - current[0] <= threshold:
                current.append(p)
            else:
                clusters.append(current)
                current = [p]
        clusters.append(current)
        levels = []
        for cluster in clusters:
            levels.append(StructureLevel(
                price=round(float(np.mean(cluster)), 2),
                level_type=level_type,
                strength=len(cluster),
                source=source,
            ))
        return levels

    result: list[StructureLevel] = []
    result.extend(cluster_prices(swing_high_prices, "resistance", "swing_high"))
    result.extend(cluster_prices(swing_low_prices, "support", "swing_low"))
    result.sort(key=lambda s: s.strength, reverse=True)
    return result


def calculate_dynamic_tp(
    direction: str,
    entry_price: float | None = None,
    atr: float | None = None,
    regime: MarketRegime | None = None,
    candles: pd.DataFrame | None = None,
    pip_size: float = PIP_SIZE,
    min_tp_pips: float = 10.0,
    *,
    entry: float | None = None,
) -> TakeProfitResult:
    """Calculate a regime-aware take-profit level using Fibonacci and S/R.

    Priority: S/R level > Fibonacci extension > ATR-based fallback.

    Args:
        direction: "BUY" or "SELL"
        entry_price: Trade entry price
        atr: Current ATR-14 value (must be > 0)
        regime: Current MarketRegime classification
        candles: Optional OHLC DataFrame for structure analysis
        pip_size: Pip size for the instrument
        min_tp_pips: Minimum TP distance in pips

    Returns:
        (take_profit, tp1, reason) where reason is "sr_zone", "fibonacci", or "atr_multiple"

    Raises:
        ValueError: If ATR is None, zero, or negative
    """
    if entry_price is None:
        if entry is None:
            raise TypeError("entry_price is required")
        entry_price = entry
    if regime is None:
        raise TypeError("regime is required")
    if atr is None or atr <= 0:
        raise ValueError(f"ATR must be positive, got: {atr}")

    params = get_regime_params(regime)
    tp_atr_multiplier = params["tp_atr_multiplier"]
    atr_tp_distance = atr * tp_atr_multiplier
    min_distance = min_tp_pips * pip_size

    # ATR-based fallback
    if direction == "BUY":
        atr_tp = entry_price + atr_tp_distance
    else:
        atr_tp = entry_price - atr_tp_distance

    best_tp: float | None = None
    reason = "atr_multiple"

    if candles is not None and len(candles) >= 5:
        # Step 3: Find S/R levels
        sr_levels = find_sr_levels(candles)
        if direction == "BUY":
            resistances = [
                s for s in sr_levels
                if s.level_type == "resistance" and s.price > entry_price + min_distance
            ]
            if resistances:
                nearest_resistance = min(resistances, key=lambda s: s.price)
                best_tp = nearest_resistance.price
                reason = "sr_zone"
        else:
            supports = [
                s for s in sr_levels
                if s.level_type == "support" and s.price < entry_price - min_distance
            ]
            if supports:
                nearest_support = max(supports, key=lambda s: s.price)
                best_tp = nearest_support.price
                reason = "sr_zone"

        # Step 4: Fibonacci extensions
        swing_data = candles.tail(50)
        if len(swing_data) >= 3:
            swing_low = float(swing_data["low"].min())
            swing_high = float(swing_data["high"].max())
            swing_range = swing_high - swing_low

            # Only compute Fibonacci if swing is meaningful (>= 2 * ATR)
            if swing_range >= 2 * atr:
                fib_levels = fibonacci_extensions(entry_price, swing_low, swing_high)
                if direction == "BUY":
                    fib_candidates = [f for f in fib_levels if f > entry_price + min_distance]
                    if fib_candidates:
                        nearest_fib = fib_candidates[0]
                        # Prefer S/R if found and closer; otherwise use fib
                        if best_tp is None or nearest_fib < best_tp:
                            best_tp = nearest_fib
                            reason = "fibonacci"
                else:
                    # For SELL: find fib levels below entry
                    # Reverse: compute extensions below swing_low
                    fib_levels_sell = [swing_low - swing_range * (r - 1.0) for r in _FIB_RATIOS]
                    fib_candidates = [f for f in sorted(fib_levels_sell, reverse=True)
                                      if f < entry_price - min_distance]
                    if fib_candidates:
                        nearest_fib = fib_candidates[0]
                        if best_tp is None or nearest_fib > best_tp:
                            best_tp = nearest_fib
                            reason = "fibonacci"

    # Use best found TP or fall back to ATR
    if best_tp is None:
        tp = atr_tp
        reason = "atr_multiple"
    else:
        tp = best_tp

    # Apply minimum floor
    if direction == "BUY":
        if tp - entry_price < min_distance:
            tp = entry_price + min_distance
        tp_distance = tp - entry_price
        tp1 = round(entry_price + tp_distance * 0.5, 2)
    else:
        if entry_price - tp < min_distance:
            tp = entry_price - min_distance
        tp_distance = entry_price - tp
        tp1 = round(entry_price - tp_distance * 0.5, 2)

    return TakeProfitResult(round(tp, 2), tp1, reason)
