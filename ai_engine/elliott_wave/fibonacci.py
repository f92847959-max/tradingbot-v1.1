"""Fibonacci math for Elliott Wave targets and retracements.

Wave 2 introduces Fibonacci projections and retracements that feed both
the scoring engine (Task 3) and downstream consumers needing TP/SL
levels.

All ratios used here are standard EWT constants. The functions are
deliberately ratio-agnostic at the call site, but the standard ratio
sets are exposed as module-level constants so callers cannot inject
arbitrary values into pattern-target computation (T-14-04 mitigation).

Conventions
-----------
* "retracement" returns a price level inside the range ``[start, end]``
  (or ``[end, start]`` if the move is down) at the requested ratio of
  the absolute move from ``end`` back toward ``start``.
* "projection" returns a price level beyond the end of the next move,
  using ``w3_start`` as the anchor and ``ratio * |w1_end - w1_start|``
  as the displacement, in the direction of the original move.
* ``get_wave_targets`` returns a dict of named target levels for a
  given :class:`~ai_engine.elliott_wave.models.WavePattern` based on
  the pattern's type — defensive against unknown / invalid patterns.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping

from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    WavePattern,
    WavePoint,
)


# ---------------------------------------------------------------------------
# Standard EWT Fibonacci ratio constants
# ---------------------------------------------------------------------------

#: Standard retracement ratios used in Elliott Wave analysis.
STANDARD_RETRACEMENT_RATIOS: tuple = (0.236, 0.382, 0.5, 0.618, 0.786)

#: Standard projection ratios for impulse-style targets (Wave 3, 5).
STANDARD_PROJECTION_RATIOS: tuple = (1.0, 1.272, 1.618, 2.0, 2.618, 4.236)

#: "Ideal" Fibonacci ratios per wave for confluence scoring.
#: Keyed by ``(PatternType, wave_label)``; value is a tuple of acceptable
#: ratios. The first entry is the most preferred. These are hardcoded —
#: external callers cannot override per the T-14-04 threat mitigation.
IDEAL_WAVE_RATIOS: Mapping = {
    # Impulse: ratios are relative to Wave 1's length (waves of impulse).
    (PatternType.IMPULSE, "2"): (0.618, 0.5, 0.382),  # Wave 2 retracement of W1
    (PatternType.IMPULSE, "3"): (1.618, 2.618, 1.0),  # Wave 3 extension of W1
    (PatternType.IMPULSE, "4"): (0.382, 0.236, 0.5),  # Wave 4 retracement of W3
    (PatternType.IMPULSE, "5"): (1.0, 0.618, 1.618),  # Wave 5 vs W1
    # Zigzag: relative to Wave A.
    (PatternType.ZIGZAG, "B"): (0.5, 0.618, 0.382),
    (PatternType.ZIGZAG, "C"): (1.0, 1.618, 0.618),
    # Flat: see scoring engine for per-subtype refinement.
    (PatternType.FLAT, "B"): (1.0, 0.9, 1.05),
    (PatternType.FLAT, "C"): (1.0, 1.618, 0.618),
    # Triangle: each leg roughly 61.8% - 78.6% of previous (contracting).
    (PatternType.TRIANGLE, "B"): (0.618, 0.786, 0.5),
    (PatternType.TRIANGLE, "C"): (0.618, 0.786, 0.5),
    (PatternType.TRIANGLE, "D"): (0.618, 0.786, 0.5),
    (PatternType.TRIANGLE, "E"): (0.618, 0.786, 0.5),
    # Diagonal: structurally similar to impulse with overlapping W4.
    (PatternType.DIAGONAL, "2"): (0.618, 0.786, 0.5),
    (PatternType.DIAGONAL, "3"): (0.618, 0.786, 1.0),
    (PatternType.DIAGONAL, "4"): (0.618, 0.786, 0.5),
    (PatternType.DIAGONAL, "5"): (0.618, 0.786, 1.0),
}


# ---------------------------------------------------------------------------
# Internal validation helpers
# ---------------------------------------------------------------------------


def _coerce_float(value, name: str) -> float:
    """Coerce numeric values to float; raise on non-numeric input."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be numeric; got {type(value).__name__}") from exc


def _validate_ratio(ratio: float) -> float:
    """Ratios must be finite and non-negative. Returns the normalised float."""
    r = _coerce_float(ratio, "ratio")
    if r != r or r in (float("inf"), float("-inf")):  # NaN/inf check
        raise ValueError("ratio must be a finite number.")
    if r < 0:
        raise ValueError(f"ratio must be non-negative; got {r}.")
    return r


# ---------------------------------------------------------------------------
# Public API: retracement / projection
# ---------------------------------------------------------------------------


def calculate_retracement(start: float, end: float, ratio: float) -> float:
    """Return the price level at ``ratio`` retracement from ``end`` back toward ``start``.

    A ``ratio`` of ``0.0`` returns ``end`` (no retracement) and ``1.0``
    returns ``start`` (full retracement). Standard ratios are exposed
    via :data:`STANDARD_RETRACEMENT_RATIOS`.

    Args:
        start: Price at the start of the move (e.g. Wave 1 start).
        end: Price at the end of the move (e.g. Wave 1 end).
        ratio: Fractional retracement, typically in ``[0, 1]`` (values
            above 1 are allowed and represent overshoots).

    Returns:
        The price level at the requested retracement.
    """
    s = _coerce_float(start, "start")
    e = _coerce_float(end, "end")
    r = _validate_ratio(ratio)
    # Move from end back toward start by ratio * (end - start).
    return e - (e - s) * r


def calculate_projection(
    w1_start: float, w1_end: float, w3_start: float, ratio: float
) -> float:
    """Project a Fibonacci target from ``w3_start`` using Wave 1's length.

    The displacement is ``ratio * |w1_end - w1_start|``, applied in the
    direction of the Wave 1 move. For a bullish Wave 1 (``w1_end >
    w1_start``), the projection extends upward from ``w3_start``; for a
    bearish Wave 1 it extends downward.

    A flat Wave 1 (``w1_end == w1_start``) yields ``w3_start`` exactly
    because the displacement is zero.

    Args:
        w1_start: Price at the start of Wave 1.
        w1_end: Price at the end of Wave 1.
        w3_start: Anchor price from which to project (typically end of W2).
        ratio: Fibonacci ratio (1.0, 1.272, 1.618, 2.618, ...).

    Returns:
        Target price level.
    """
    a = _coerce_float(w1_start, "w1_start")
    b = _coerce_float(w1_end, "w1_end")
    c = _coerce_float(w3_start, "w3_start")
    r = _validate_ratio(ratio)
    w1_len = abs(b - a)
    direction = 1 if b >= a else -1
    return c + direction * w1_len * r


# ---------------------------------------------------------------------------
# Pattern-level helpers
# ---------------------------------------------------------------------------


def get_wave_targets(pattern: WavePattern) -> Dict[str, float]:
    """Return a dict of named Fibonacci target levels for ``pattern``.

    The set of targets depends on :attr:`WavePattern.pattern_type`. The
    function is defensive: malformed or unsupported patterns return an
    empty dict rather than raising, so callers can fold this into a
    rendering pipeline without try/except wrappers.

    Args:
        pattern: A candidate :class:`WavePattern`. Need not be valid.

    Returns:
        A mapping from target label (e.g. ``"w3_1.618"``) to price.
    """
    if pattern is None or not pattern.points:
        return {}

    points = pattern.points

    if pattern.pattern_type == PatternType.IMPULSE and len(points) >= 3:
        return _impulse_targets(points)
    if pattern.pattern_type == PatternType.DIAGONAL and len(points) >= 3:
        return _impulse_targets(points)  # Same projection math
    if pattern.pattern_type == PatternType.ZIGZAG and len(points) >= 3:
        return _zigzag_targets(points)
    if pattern.pattern_type == PatternType.FLAT and len(points) >= 3:
        return _flat_targets(points)
    if pattern.pattern_type == PatternType.TRIANGLE and len(points) >= 2:
        return _triangle_targets(points)
    return {}


def _impulse_targets(points) -> Dict[str, float]:
    """Targets for an impulse: W3 and W5 projections from observed W1."""
    p0, p1 = points[0], points[1]  # W1 start, W1 end
    targets: Dict[str, float] = {}

    # W3 targets projected from end-of-W2 if available, else end-of-W1.
    w3_anchor = points[2].price if len(points) >= 3 else p1.price
    for ratio in (1.0, 1.272, 1.618, 2.618):
        key = f"w3_{ratio}"
        targets[key] = calculate_projection(p0.price, p1.price, w3_anchor, ratio)

    # W2 retracement levels (informational; used for entry analysis).
    for ratio in (0.382, 0.5, 0.618, 0.786):
        targets[f"w2_retracement_{ratio}"] = calculate_retracement(
            p0.price, p1.price, ratio
        )

    # W5 targets projected from end-of-W4 if available.
    if len(points) >= 5:
        w5_anchor = points[4].price
        for ratio in (0.618, 1.0, 1.618):
            targets[f"w5_{ratio}"] = calculate_projection(
                p0.price, p1.price, w5_anchor, ratio
            )

    return targets


def _zigzag_targets(points) -> Dict[str, float]:
    """Targets for a zigzag: C-wave projections from end-of-B."""
    a_start, a_end = points[0], points[1]
    targets: Dict[str, float] = {}

    for ratio in (0.382, 0.5, 0.618, 0.786):
        targets[f"b_retracement_{ratio}"] = calculate_retracement(
            a_start.price, a_end.price, ratio
        )

    if len(points) >= 3:
        b_end = points[2]
        for ratio in (0.618, 1.0, 1.618):
            targets[f"c_{ratio}"] = calculate_projection(
                a_start.price, a_end.price, b_end.price, ratio
            )
    return targets


def _flat_targets(points) -> Dict[str, float]:
    """Targets for a flat: C-wave projections at 1.0 / 1.618 of A."""
    a_start, a_end = points[0], points[1]
    targets: Dict[str, float] = {}
    if len(points) >= 3:
        b_end = points[2]
        for ratio in (1.0, 1.272, 1.618):
            targets[f"c_{ratio}"] = calculate_projection(
                a_start.price, a_end.price, b_end.price, ratio
            )
    return targets


def _triangle_targets(points) -> Dict[str, float]:
    """Targets for a triangle: contracting boundaries (next-leg projections)."""
    targets: Dict[str, float] = {}
    # For each leg, the next leg is expected to be ~ 0.618-0.786 of the prior.
    for i in range(len(points) - 1):
        leg_start, leg_end = points[i], points[i + 1]
        for ratio in (0.618, 0.786):
            key = f"leg{i + 1}_{ratio}"
            targets[key] = calculate_retracement(leg_start.price, leg_end.price, ratio)
    return targets


__all__ = [
    "IDEAL_WAVE_RATIOS",
    "STANDARD_PROJECTION_RATIOS",
    "STANDARD_RETRACEMENT_RATIOS",
    "calculate_projection",
    "calculate_retracement",
    "get_wave_targets",
]
