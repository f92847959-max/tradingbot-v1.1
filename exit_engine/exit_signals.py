"""Exit signal detector: reversal candle patterns and momentum divergence.

Scans recent candles for patterns that suggest a trade should be exited
before the full TP or SL is reached.
"""

from __future__ import annotations

import logging

import pandas as pd

from exit_engine.types import ExitSignal

logger = logging.getLogger(__name__)


def check_exit_signals(
    direction: str,
    candles: pd.DataFrame,
    lookback: int = 5,
) -> ExitSignal:
    """Check recent candles for exit-worthy reversal patterns.

    Priority: reversal candle (confidence 0.7) > momentum divergence (0.6).

    Args:
        direction: "BUY" or "SELL" — direction of the open position
        candles: OHLC DataFrame; optionally includes 'rsi_14' column
        lookback: Number of recent candles to inspect

    Returns:
        ExitSignal with should_exit flag, signal type, confidence, and reason
    """
    if len(candles) < 2:
        return ExitSignal(
            should_exit=False,
            signal_type="none",
            confidence=0.0,
            reason="insufficient candles",
        )

    recent = candles.tail(lookback)
    prev = recent.iloc[-2]
    curr = recent.iloc[-1]

    # ------------------------------------------------------------------
    # Check 1: Reversal candle patterns
    # ------------------------------------------------------------------
    if direction == "BUY":
        # Bearish engulfing
        prev_bullish = prev["close"] > prev["open"]
        curr_bearish = curr["close"] < curr["open"]
        if prev_bullish and curr_bearish:
            curr_body = abs(curr["close"] - curr["open"])
            prev_body = abs(prev["close"] - prev["open"])
            engulfs = (
                curr["open"] >= prev["close"]
                and curr["close"] <= prev["open"]
                and curr_body > prev_body
            )
            if engulfs:
                return ExitSignal(
                    should_exit=True,
                    signal_type="reversal_candle",
                    confidence=0.7,
                    reason="bearish engulfing pattern detected",
                )

        # Shooting star: small body at bottom, long upper wick >= 2x body
        body = abs(curr["close"] - curr["open"])
        upper_wick = curr["high"] - max(curr["open"], curr["close"])
        if body > 0 and upper_wick >= 2.0 * body and curr["close"] < curr["open"]:
            return ExitSignal(
                should_exit=True,
                signal_type="reversal_candle",
                confidence=0.65,
                reason="shooting star pattern detected",
            )

    else:  # SELL
        # Bullish engulfing
        prev_bearish = prev["close"] < prev["open"]
        curr_bullish = curr["close"] > curr["open"]
        if prev_bearish and curr_bullish:
            curr_body = abs(curr["close"] - curr["open"])
            prev_body = abs(prev["close"] - prev["open"])
            engulfs = (
                curr["open"] <= prev["close"]
                and curr["close"] >= prev["open"]
                and curr_body > prev_body
            )
            if engulfs:
                return ExitSignal(
                    should_exit=True,
                    signal_type="reversal_candle",
                    confidence=0.7,
                    reason="bullish engulfing pattern detected",
                )

        # Hammer: small body at top, long lower wick >= 2x body
        body = abs(curr["close"] - curr["open"])
        lower_wick = min(curr["open"], curr["close"]) - curr["low"]
        if body > 0 and lower_wick >= 2.0 * body and curr["close"] > curr["open"]:
            return ExitSignal(
                should_exit=True,
                signal_type="reversal_candle",
                confidence=0.65,
                reason="hammer pattern detected",
            )

    # ------------------------------------------------------------------
    # Check 2: Momentum divergence (requires rsi_14 column)
    # ------------------------------------------------------------------
    if "rsi_14" in candles.columns:
        # Compare last candle vs candle at position -(lookback) relative to end
        window = candles.tail(lookback)
        first = window.iloc[0]
        last = window.iloc[-1]

        if direction == "BUY":
            # Bearish divergence: price higher high but RSI lower high
            price_higher = last["close"] > first["close"]
            rsi_lower = last["rsi_14"] < first["rsi_14"]
            if price_higher and rsi_lower:
                return ExitSignal(
                    should_exit=True,
                    signal_type="momentum_divergence",
                    confidence=0.6,
                    reason="bearish RSI divergence: price higher high but RSI lower",
                )
        else:
            # Bullish divergence: price lower low but RSI higher low
            price_lower = last["close"] < first["close"]
            rsi_higher = last["rsi_14"] > first["rsi_14"]
            if price_lower and rsi_higher:
                return ExitSignal(
                    should_exit=True,
                    signal_type="momentum_divergence",
                    confidence=0.6,
                    reason="bullish RSI divergence: price lower low but RSI higher",
                )

    # Nothing detected
    return ExitSignal(
        should_exit=False,
        signal_type="none",
        confidence=0.0,
        reason="no exit signal",
    )
