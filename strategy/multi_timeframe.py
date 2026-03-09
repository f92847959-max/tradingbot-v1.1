"""Multi-timeframe analysis — checks trend alignment across timeframes."""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def check_alignment(
    data: dict[str, pd.DataFrame],
    direction: Optional[str] = None,
) -> float:
    """Check EMA trend alignment across multiple timeframes.

    For each timeframe, checks if EMA-9 > EMA-21 (bullish) or EMA-9 < EMA-21 (bearish).
    Returns the fraction of timeframes that agree on direction.

    Args:
        data: Dict mapping timeframe string to DataFrame with 'ema_9' and 'ema_21' columns.
              E.g. {"1m": df1, "5m": df5, "15m": df15}
        direction: Optional "BUY" or "SELL" to check alignment for specific direction.
                   If None, returns alignment with the majority direction.

    Returns:
        Float 0.0-1.0 representing fraction of aligned timeframes.
        0.0 = no alignment, 1.0 = perfect alignment.
    """
    if not data:
        return 0.0

    bullish_count = 0
    bearish_count = 0
    valid_count = 0

    for tf, df in data.items():
        if df is None or df.empty:
            continue
        if "ema_9" not in df.columns or "ema_21" not in df.columns:
            logger.warning("Missing ema_9/ema_21 in timeframe %s — skipping", tf)
            continue

        last = df.iloc[-1]
        ema_9 = last.get("ema_9")
        ema_21 = last.get("ema_21")

        if pd.isna(ema_9) or pd.isna(ema_21):
            continue

        valid_count += 1
        if ema_9 > ema_21:
            bullish_count += 1
        else:
            bearish_count += 1

    if valid_count == 0:
        return 0.0

    if direction == "BUY":
        return bullish_count / valid_count
    elif direction == "SELL":
        return bearish_count / valid_count
    else:
        # Return alignment with majority direction
        majority = max(bullish_count, bearish_count)
        return majority / valid_count


def get_dominant_direction(data: dict[str, pd.DataFrame]) -> Optional[str]:
    """Return the dominant trend direction across timeframes, or None if mixed."""
    if not data:
        return None

    bullish = 0
    bearish = 0

    for tf, df in data.items():
        if df is None or df.empty:
            continue
        if "ema_9" not in df.columns or "ema_21" not in df.columns:
            continue

        last = df.iloc[-1]
        ema_9 = last.get("ema_9")
        ema_21 = last.get("ema_21")

        if pd.isna(ema_9) or pd.isna(ema_21):
            continue

        if ema_9 > ema_21:
            bullish += 1
        else:
            bearish += 1

    total = bullish + bearish
    if total == 0:
        return None
    if bullish > bearish:
        return "BUY"
    if bearish > bullish:
        return "SELL"
    return None  # 50/50 split — no clear direction
