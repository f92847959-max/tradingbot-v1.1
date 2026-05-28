"""Fibonacci confluence scoring for Elliott Wave patterns (Phase 14-02).

The rule engine in :mod:`ai_engine.elliott_wave.rules` emits every
candidate that satisfies the structural rules — but in any real market,
multiple valid counts coexist (Pitfall 2 in 14-RESEARCH.md). The scoring
engine here ranks those candidates by how closely their internal wave
ratios match the standard EWT Fibonacci constants.

Design
------
* :func:`score_pattern` returns a float in ``[0, 1]``:
    - ``0.0`` for invalid patterns (no signal).
    - ``1.0`` for a perfect match against the most-preferred ideal ratio.
    - Intermediate values for partial confluence.
* :func:`get_primary_count` picks the highest-scoring valid pattern from
  a list of candidates. Tie-break order is deterministic:
    1. Higher score wins.
    2. Higher EWT pattern preference wins (Impulse > Zigzag > others).
    3. First occurrence wins (stable sort).
* :func:`rank_patterns` returns ``(pattern, score)`` pairs sorted by
  score descending — useful for diagnostics and alternative counts.

Threat model (T-14-04 — Tampering on scoring):
    All ratio constants are loaded from
    :data:`ai_engine.elliott_wave.fibonacci.IDEAL_WAVE_RATIOS`. No
    caller-supplied ratio table is accepted, so an attacker cannot
    inject overly-permissive ratios that promote weak patterns.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ai_engine.elliott_wave.fibonacci import IDEAL_WAVE_RATIOS
from ai_engine.elliott_wave.models import (
    PatternType,
    WavePattern,
    WavePoint,
)


# ---------------------------------------------------------------------------
# Tunables (module-level constants; not externally configurable to satisfy T-14-04)
# ---------------------------------------------------------------------------

#: Maximum acceptable proportional error vs an ideal ratio before the
#: per-wave score floors at 0. Beyond this, the wave is treated as a
#: structural pass but a confluence failure.
_MAX_ERROR: float = 0.40

#: Penalty applied per recorded violation in the pattern. Sub-type tags
#: (``sub_type=*``) are not violations and do not contribute.
_PER_VIOLATION_PENALTY: float = 0.20

#: Weight given to "barely valid" patterns (no violations but no
#: confluence either). Floors the score at this value.
_BARELY_VALID_FLOOR: float = 0.05

#: Pattern preference for tie-break (higher index = stronger preference).
_PATTERN_PRIORITY: dict = {
    PatternType.IMPULSE: 5,
    PatternType.DIAGONAL: 4,
    PatternType.ZIGZAG: 3,
    PatternType.FLAT: 2,
    PatternType.TRIANGLE: 1,
    PatternType.COMPLEX: 0,
    PatternType.NONE: -1,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wave_ratio(actual: float, reference: float) -> Optional[float]:
    """Safe ratio computation; returns None if reference is zero."""
    if reference == 0:
        return None
    return actual / reference


def _ratio_score(actual_ratio: float, ideal_ratios: Sequence[float]) -> float:
    """Score how close ``actual_ratio`` is to the most-preferred ideal.

    Returns ``1.0`` for a perfect match against any ideal in the
    sequence (weighted by position: first ideal has full weight, later
    ones decay), and ``0.0`` when the error exceeds :data:`_MAX_ERROR`
    against every ideal.

    The score for each ideal is:
        ``max(0, 1 - error/_MAX_ERROR) * weight``
    The maximum across all ideals is returned, so a pattern matching
    *any* canonical ratio scores well.
    """
    if not ideal_ratios:
        return 0.0
    best = 0.0
    for i, ideal in enumerate(ideal_ratios):
        weight = 1.0 if i == 0 else 0.85 if i == 1 else 0.7
        if ideal == 0:
            continue
        error = abs(actual_ratio - ideal) / ideal
        if error >= _MAX_ERROR:
            continue
        s = (1.0 - error / _MAX_ERROR) * weight
        if s > best:
            best = s
    return best


def _impulse_wave_scores(points: Sequence[WavePoint]) -> List[float]:
    """Compute per-wave confluence scores for an impulse pattern."""
    if len(points) < 6:
        return []
    p0, p1, p2, p3, p4, p5 = points[:6]
    w1_len = abs(p1.price - p0.price)
    w2_len = abs(p2.price - p1.price)
    w3_len = abs(p3.price - p2.price)
    w4_len = abs(p4.price - p3.price)
    w5_len = abs(p5.price - p4.price)

    scores: List[float] = []
    # W2 retracement of W1.
    r = _wave_ratio(w2_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.IMPULSE, "2"), ()))
        )
    # W3 extension of W1.
    r = _wave_ratio(w3_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.IMPULSE, "3"), ()))
        )
    # W4 retracement of W3.
    r = _wave_ratio(w4_len, w3_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.IMPULSE, "4"), ()))
        )
    # W5 vs W1.
    r = _wave_ratio(w5_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.IMPULSE, "5"), ()))
        )
    return scores


def _zigzag_wave_scores(points: Sequence[WavePoint]) -> List[float]:
    """Compute per-wave confluence scores for a zigzag pattern."""
    if len(points) < 4:
        return []
    a_start, a_end, b_end, c_end = points[:4]
    a_len = abs(a_end.price - a_start.price)
    b_len = abs(b_end.price - a_end.price)
    c_len = abs(c_end.price - b_end.price)

    scores: List[float] = []
    r = _wave_ratio(b_len, a_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.ZIGZAG, "B"), ()))
        )
    r = _wave_ratio(c_len, a_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.ZIGZAG, "C"), ()))
        )
    return scores


def _flat_wave_scores(points: Sequence[WavePoint]) -> List[float]:
    if len(points) < 4:
        return []
    a_start, a_end, b_end, c_end = points[:4]
    a_len = abs(a_end.price - a_start.price)
    b_len = abs(b_end.price - a_end.price)
    c_len = abs(c_end.price - b_end.price)

    scores: List[float] = []
    r = _wave_ratio(b_len, a_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.FLAT, "B"), ()))
        )
    r = _wave_ratio(c_len, a_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.FLAT, "C"), ()))
        )
    return scores


def _triangle_wave_scores(points: Sequence[WavePoint]) -> List[float]:
    if len(points) < 6:
        return []
    scores: List[float] = []
    labels = ("B", "C", "D", "E")
    for i in range(1, len(points) - 1):
        prev_leg = abs(points[i].price - points[i - 1].price)
        cur_leg = abs(points[i + 1].price - points[i].price)
        r = _wave_ratio(cur_leg, prev_leg)
        if r is None:
            continue
        label = labels[i - 1] if i - 1 < len(labels) else labels[-1]
        ideal = IDEAL_WAVE_RATIOS.get((PatternType.TRIANGLE, label), ())
        scores.append(_ratio_score(r, ideal))
    return scores


def _diagonal_wave_scores(points: Sequence[WavePoint]) -> List[float]:
    if len(points) < 6:
        return []
    p0, p1, p2, p3, p4, p5 = points[:6]
    w1_len = abs(p1.price - p0.price)
    w2_len = abs(p2.price - p1.price)
    w3_len = abs(p3.price - p2.price)
    w4_len = abs(p4.price - p3.price)
    w5_len = abs(p5.price - p4.price)

    scores: List[float] = []
    r = _wave_ratio(w2_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.DIAGONAL, "2"), ()))
        )
    r = _wave_ratio(w3_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.DIAGONAL, "3"), ()))
        )
    r = _wave_ratio(w4_len, w3_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.DIAGONAL, "4"), ()))
        )
    r = _wave_ratio(w5_len, w1_len)
    if r is not None:
        scores.append(
            _ratio_score(r, IDEAL_WAVE_RATIOS.get((PatternType.DIAGONAL, "5"), ()))
        )
    return scores


def _structural_violations(pattern: WavePattern) -> int:
    """Count true rule violations, ignoring informational sub-type tags."""
    return sum(1 for v in pattern.violations if not v.startswith("sub_type="))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def score_pattern(pattern: WavePattern) -> float:
    """Score a :class:`WavePattern` by Fibonacci confluence.

    Invalid patterns receive ``0.0``. Valid patterns are scored as the
    mean of per-wave confluence scores, with a small penalty per
    structural violation (defensive — valid patterns rarely have any,
    but the engine may emit ``include_invalid=True`` candidates).

    The function reads ideal ratios from
    :data:`~ai_engine.elliott_wave.fibonacci.IDEAL_WAVE_RATIOS` only —
    callers cannot inject custom ratios (T-14-04).

    Args:
        pattern: A candidate pattern from the rule engine.

    Returns:
        Score in ``[0.0, 1.0]``. Higher means closer to the canonical
        Fibonacci structure for that pattern type.
    """
    if pattern is None or not pattern.is_valid:
        return 0.0

    if pattern.pattern_type == PatternType.IMPULSE:
        wave_scores = _impulse_wave_scores(pattern.points)
    elif pattern.pattern_type == PatternType.ZIGZAG:
        wave_scores = _zigzag_wave_scores(pattern.points)
    elif pattern.pattern_type == PatternType.FLAT:
        wave_scores = _flat_wave_scores(pattern.points)
    elif pattern.pattern_type == PatternType.TRIANGLE:
        wave_scores = _triangle_wave_scores(pattern.points)
    elif pattern.pattern_type == PatternType.DIAGONAL:
        wave_scores = _diagonal_wave_scores(pattern.points)
    else:
        wave_scores = []

    if not wave_scores:
        return _BARELY_VALID_FLOOR

    base = sum(wave_scores) / len(wave_scores)
    violations = _structural_violations(pattern)
    penalised = max(0.0, base - violations * _PER_VIOLATION_PENALTY)
    # Floor: even a barely-valid pattern with no confluence should get
    # a sliver of credit so the engine still ranks it above invalids.
    return max(_BARELY_VALID_FLOOR, penalised)


def rank_patterns(patterns: Sequence[WavePattern]) -> List[Tuple[WavePattern, float]]:
    """Return ``(pattern, score)`` pairs sorted by score descending.

    Stable: patterns with identical scores retain their input order
    (after applying the pattern-type preference tie-break).
    """
    pairs = [(p, score_pattern(p)) for p in patterns]

    def sort_key(item: Tuple[WavePattern, float]) -> Tuple[float, int]:
        pattern, score = item
        # Negative score so higher scores sort first; pattern priority
        # also negated so higher priority sorts first.
        priority = _PATTERN_PRIORITY.get(pattern.pattern_type, -1)
        return (-score, -priority)

    return sorted(pairs, key=sort_key)


def get_primary_count(patterns: Sequence[WavePattern]) -> Optional[WavePattern]:
    """Return the single highest-confluence pattern from ``patterns``.

    Returns ``None`` if ``patterns`` is empty or contains no valid
    candidates. Tie-break follows :func:`rank_patterns`.
    """
    if not patterns:
        return None
    ranked = rank_patterns(patterns)
    if not ranked:
        return None
    top_pattern, top_score = ranked[0]
    if not top_pattern.is_valid or top_score <= 0:
        return None
    return top_pattern


__all__ = [
    "get_primary_count",
    "rank_patterns",
    "score_pattern",
]
