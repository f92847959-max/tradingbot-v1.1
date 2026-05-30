"""Elliott Wave structural context builder for MiroFish agents (Phase 14-03).

Provides the ``build_wave_context`` function that converts an OHLCV DataFrame
into a human-readable narrative string describing the primary Elliott Wave
count and Fibonacci targets.

The resulting string is injected into the ``## Structural Context`` section of
MiroFish agent prompts via ``MiroFishClient._prepare_prompt``.

Threat mitigations
------------------
T-14-05 (Prompt injection via crafted price data): All strings derived from
price data are sanitised through ``sanitise_context_string`` before injection.
Control characters are stripped and the string is capped at ``MAX_CONTEXT_LEN``
characters.

T-14-06 (DoS in feature extraction): The OHLCV window fed to WaveDetector is
capped at ``EW_MAX_WINDOW`` rows (re-exported from
``elliott_wave_features``).  On Windows, signal-based timeouts are
unavailable; bounded input size is the sole DoS guard.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

#: Maximum length (characters) for the injected wave context string (T-14-05).
MAX_CONTEXT_LEN: int = 500


def sanitise_context_string(text: str) -> str:
    """Sanitise an Elliott Wave context string before prompt injection.

    Removes ASCII control characters (except ordinary whitespace: space,
    tab, newline, carriage return) and truncates to ``MAX_CONTEXT_LEN``
    characters.  Guards against prompt-injection via crafted price data
    (T-14-05).

    Args:
        text: Raw context string derived from price data.

    Returns:
        Sanitised, length-capped string safe for prompt injection.
    """
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    if len(cleaned) > MAX_CONTEXT_LEN:
        cleaned = cleaned[:MAX_CONTEXT_LEN] + "…"
    return cleaned


def build_wave_context(market_data: dict) -> str:
    """Derive the Elliott Wave narrative from ``market_data``.

    Runs ``WaveDetector`` + ``RuleEngine`` + ``get_primary_count`` on the
    OHLCV data in ``market_data["ohlcv_df"]`` and returns a human-readable
    English string describing the primary wave count and Fibonacci targets.

    Args:
        market_data: Dict optionally containing:
            - ``ohlcv_df``: pandas DataFrame with a ``close`` column.
              Other keys (``current_price``, ``timeframe``) are ignored here.

    Returns:
        A plain-text string describing the wave count, or a safe fallback
        message when no count is available.
    """
    ohlcv_df: Optional[pd.DataFrame] = market_data.get("ohlcv_df")
    if ohlcv_df is None or (hasattr(ohlcv_df, "empty") and ohlcv_df.empty):
        return "No Elliott Wave count available — insufficient market data."

    try:
        from ai_engine.elliott_wave.detector import WaveDetector
        from ai_engine.elliott_wave.fibonacci import get_wave_targets
        from ai_engine.elliott_wave.rules import RuleEngine
        from ai_engine.elliott_wave.scoring import get_primary_count
        from ai_engine.features.elliott_wave_features import EW_MAX_WINDOW

        df_window = ohlcv_df.iloc[-EW_MAX_WINDOW:]

        if "close" not in df_window.columns:
            return "No Elliott Wave count available — 'close' column missing."

        df_clean = df_window.dropna(subset=["close"])
        if len(df_clean) < 6:
            return "No Elliott Wave count available — insufficient clean candles."

        detector = WaveDetector()
        swings = detector.detect_swings(df_clean, price_column="close")
        if len(swings) < 4:
            return "No Elliott Wave count available — too few swing points detected."

        engine = RuleEngine()
        candidates = engine.scan(swings)
        primary = get_primary_count(candidates)
        if primary is None:
            return "No valid Elliott Wave count detected in current price structure."

        waves = primary.waves
        wave_count = len(waves)
        last_label = waves[-1].label if waves else "?"
        pattern_name = primary.pattern_type.value.capitalize()
        direction_word = "Bullish" if primary.direction >= 0 else "Bearish"

        targets = get_wave_targets(primary)
        target_lines = []
        for target_name, target_price in list(targets.items())[:3]:
            target_lines.append(f"  {target_name}: {target_price:.2f}")
        target_text = (
            "Fibonacci targets:\n" + "\n".join(target_lines)
            if target_lines
            else "No Fibonacci targets available."
        )

        return (
            f"Gold is currently in Wave {last_label} of a "
            f"{direction_word} {pattern_name} pattern "
            f"({wave_count} waves confirmed).\n"
            f"{target_text}"
        )

    except Exception as exc:
        logger.debug("EW context build failed (non-fatal): %s", exc)
        return "No Elliott Wave count available — analysis error."


def prepare_structural_prompt(market_data: dict) -> str:
    """Build the full ``## Structural Context`` prompt section.

    Combines the raw wave narrative with sanitisation and optional
    price/timeframe metadata lines.

    Args:
        market_data: Dict with optional keys ``ohlcv_df``, ``current_price``,
            ``timeframe``.

    Returns:
        Multi-line string starting with ``## Structural Context``.
    """
    wave_context = build_wave_context(market_data)
    sanitised = sanitise_context_string(wave_context)

    timeframe = market_data.get("timeframe", "5m")
    current_price = market_data.get("current_price", None)

    lines = [
        "## Structural Context",
        "",
        sanitised,
    ]
    if current_price is not None:
        lines.extend(["", f"Current price: {current_price:.2f}"])
    if timeframe:
        lines.extend(["", f"Timeframe: {timeframe}"])

    return "\n".join(lines)
