"""Elliott Wave ML feature group (Phase 14-03).

Extracts 4 causal Elliott Wave features from an OHLCV DataFrame and appends
them as new columns.  The features are computed causally — only data up to
each candle's own row is used — by running the ``WaveDetector`` + scoring
pipeline once on the full incoming window (no lookahead across rows).

Features
--------
ew_pattern_type : int
    Encoded pattern category for the primary count.
    0 = no count / NONE
    1 = IMPULSE
    2 = ZIGZAG
    3 = FLAT
    4 = TRIANGLE
    5 = DIAGONAL
    6 = COMPLEX

ew_wave_number : int
    Position of the most recent confirmed wave in the count.
    Impulse/Diagonal: 1–5.  Corrective (ABC): 1=A, 2=B, 3=C.  0 = unknown.

ew_completion : float
    Estimated completion of the current active wave as a fraction [0, 1].
    Computed as price-distance from the last swing to the next Fibonacci
    target divided by the target distance.  Falls back to 0.0 when no
    target is available.

ew_is_motive : int  (bool encoded as 0/1 for ML compatibility)
    1 when the primary count is a motive pattern (Impulse or Diagonal),
    0 for corrective patterns or when no count is available.

Threat mitigations
------------------
T-14-06 (DoS): The detector input is capped at ``EW_MAX_WINDOW`` rows before
being passed to ``WaveDetector``.  On Windows, SIGALRM is unavailable; the
cap ensures bounded compute (see 14-03 SUMMARY for rationale).

T-14-05 (Prompt injection): Not applicable here; this module produces numeric
features only.  The MiroFish context string is sanitised in
``mirofish_client._prepare_prompt``.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

from ai_engine.elliott_wave.detector import WaveDetector
from ai_engine.elliott_wave.fibonacci import get_wave_targets
from ai_engine.elliott_wave.models import PatternType, WavePattern
from ai_engine.elliott_wave.rules import RuleEngine
from ai_engine.elliott_wave.scoring import get_primary_count

logger = logging.getLogger(__name__)

# Hard cap on the candle window fed to the WaveDetector (T-14-06 mitigation).
# On Windows, signal-based timeouts are unavailable; we bound compute by input
# size instead.  300 candles is far more than needed for a clean 5-wave count.
EW_MAX_WINDOW: int = 300

# Pattern type -> int encoding expected by the ML model.
_PATTERN_ENCODING = {
    PatternType.NONE: 0,
    PatternType.IMPULSE: 1,
    PatternType.ZIGZAG: 2,
    PatternType.FLAT: 3,
    PatternType.TRIANGLE: 4,
    PatternType.DIAGONAL: 5,
    PatternType.COMPLEX: 6,
}

_MOTIVE_PATTERNS = {PatternType.IMPULSE, PatternType.DIAGONAL}

# Feature names (module-level constant so callers can introspect without
# creating an instance).
FEATURE_NAMES: List[str] = [
    "ew_pattern_type",
    "ew_wave_number",
    "ew_completion",
    "ew_is_motive",
]


def _zero_features() -> dict:
    """Return a dict with all EW features defaulted to 0."""
    return {name: 0 for name in FEATURE_NAMES}


def _wave_number_from_pattern(pattern: WavePattern) -> int:
    """Extract the last wave number from a pattern.

    For impulse / diagonal returns 1-5; for corrective returns 1=A, 2=B, 3=C.
    Returns 0 when the label cannot be parsed.
    """
    waves = pattern.waves
    if not waves:
        return 0
    last_label = waves[-1].label
    _corrective_map = {"A": 1, "B": 2, "C": 3}
    if last_label in _corrective_map:
        return _corrective_map[last_label]
    try:
        return int(last_label)
    except (ValueError, TypeError):
        return 0


def _completion_from_pattern(pattern: WavePattern, current_price: float) -> float:
    """Estimate the completion fraction [0, 1] of the last active wave.

    Uses Fibonacci targets from ``get_wave_targets``.  The first available
    target determines the range.  Returns 0.0 on any error.
    """
    try:
        targets = get_wave_targets(pattern)
        if not targets:
            return 0.0

        waves = pattern.waves
        if not waves:
            return 0.0

        last_wave = waves[-1]
        start_price = last_wave.start.price
        # Take the first target as the projection end.
        target_price = next(iter(targets.values()))

        total_distance = abs(target_price - start_price)
        if total_distance < 1e-9:
            return 0.0

        traveled = abs(current_price - start_price)
        return float(min(1.0, max(0.0, traveled / total_distance)))
    except Exception:
        return 0.0


def extract_ew_features(ohlcv_df: pd.DataFrame) -> dict:
    """Run the EW pipeline on ``ohlcv_df`` and return a feature dict.

    The computation uses only the last ``EW_MAX_WINDOW`` rows (T-14-06)
    and is treated as a snapshot of the market at the current candle.
    No lookahead across rows is introduced — callers who need per-row
    features should call this once per new candle and broadcast the result
    to all rows of that candle.

    Args:
        ohlcv_df: DataFrame with at least a ``close`` column, NaN-free.

    Returns:
        Dict with keys ``ew_pattern_type``, ``ew_wave_number``,
        ``ew_completion``, ``ew_is_motive`` and their computed values.
    """
    features = _zero_features()

    if ohlcv_df is None or ohlcv_df.empty:
        return features

    if "close" not in ohlcv_df.columns:
        return features

    # T-14-06: cap the window before expensive detection.
    df_window = ohlcv_df.iloc[-EW_MAX_WINDOW:].copy()

    # Drop rows with NaN in close to satisfy detector preconditions.
    df_window = df_window.dropna(subset=["close"])
    if len(df_window) < 6:  # Need at least 6 points for the shortest pattern.
        return features

    try:
        detector = WaveDetector()
        swings = detector.detect_swings(df_window, price_column="close")

        if len(swings) < 4:
            return features

        engine = RuleEngine()
        candidates = engine.scan(swings)

        primary: Optional[WavePattern] = get_primary_count(candidates)
        if primary is None:
            return features

        current_price = float(df_window["close"].iloc[-1])

        features["ew_pattern_type"] = _PATTERN_ENCODING.get(primary.pattern_type, 0)
        features["ew_wave_number"] = _wave_number_from_pattern(primary)
        features["ew_completion"] = _completion_from_pattern(primary, current_price)
        features["ew_is_motive"] = int(primary.pattern_type in _MOTIVE_PATTERNS)

    except Exception as exc:
        logger.debug("EW feature extraction failed (non-fatal): %s", exc)
        # Return zeros — feature pipeline must never crash.

    return features


class ElliottWaveFeatures:
    """Feature group wrapper following the FeatureEngineer sub-class protocol.

    ``get_feature_names()`` returns the 4 EW feature names.
    ``calculate(df)`` appends the features to the DataFrame and returns it.
    """

    def __init__(self, ew_enabled: bool = True) -> None:
        self._ew_enabled = ew_enabled

    def get_feature_names(self) -> List[str]:
        return FEATURE_NAMES.copy()

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Append EW features to ``df``.

        Features are computed once on the whole incoming window (causal: last
        candle only) and broadcast uniformly to every row.  This avoids
        lookahead while keeping the feature matrix aligned.

        When EW extraction is disabled (``ew_enabled=False``) all columns
        are filled with zeros so downstream code never sees missing columns.
        """
        if not self._ew_enabled:
            for name in FEATURE_NAMES:
                df[name] = 0
            return df

        features = extract_ew_features(df)
        for name in FEATURE_NAMES:
            df[name] = features.get(name, 0)
        return df
