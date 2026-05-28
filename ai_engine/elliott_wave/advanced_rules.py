"""Advanced Elliott Wave rule classes (Phase 14-02).

Ships rule validators for the EWT pattern families that go beyond the
core Impulse/Zigzag pair handled in Wave 1:

* :class:`DiagonalRule` — Leading and Ending Diagonals. Five waves like
  an impulse, but Wave 4 is *allowed* to overlap Wave 1's territory.
  Contracting diagonals additionally require ``W1 > W3 > W5`` in
  absolute length.

* :class:`FlatRule` — Regular, Expanded, and Running flats. Three-wave
  corrective with ``A``, ``B``, ``C`` where:
    - Regular:  ``|B| in [0.9, 1.05] * |A|`` and ``C`` ends near ``A``.
    - Expanded: ``|B| > 1.0 * |A|`` and ``|C| > 1.0 * |B|``.
    - Running:  ``B`` exceeds ``A``'s start, but ``C`` falls short of
      ``A``'s end (weaker correction in a strong trend).

* :class:`TriangleRule` — Contracting and Expanding triangles. Five
  legs (``a-b-c-d-e``) producing six extrema. Each contracting leg is
  ~61.8-78.6% of the previous; expanding triangles invert the ratio.

Each rule returns a :class:`~ai_engine.elliott_wave.models.WavePattern`
populated with concrete sub-type metadata in ``violations`` /
``direction`` so the scoring engine in Task 3 can prefer canonical sub-
types.

Threat model (T-14-04): rule classes encapsulate behaviour; no
external configuration of ratio thresholds is exposed.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    WavePattern,
    WavePoint,
)
from ai_engine.elliott_wave.rules import BaseRule


# Standard tolerance for "approximately equal" comparisons. Expressed
# as a fractional margin of the reference length.
_APPROX_EQUAL_TOLERANCE: float = 0.10  # +/-10%

# Flat sub-type thresholds (per EWT canon).
_FLAT_REGULAR_B_LOW: float = 0.90
_FLAT_REGULAR_B_HIGH: float = 1.05
_FLAT_EXPANDED_B_MIN: float = 1.00
_FLAT_EXPANDED_C_MIN: float = 1.00

# Triangle leg-ratio bounds (next leg / previous leg). Contracting
# triangles compress toward the apex; expanding triangles broaden out.
_TRIANGLE_CONTRACTING_LOW: float = 0.50
_TRIANGLE_CONTRACTING_HIGH: float = 0.95
_TRIANGLE_EXPANDING_LOW: float = 1.05
_TRIANGLE_EXPANDING_HIGH: float = 2.00


def _length(a: WavePoint, b: WavePoint) -> float:
    return abs(b.price - a.price)


def _indices_strict(points: Sequence[WavePoint]) -> List[str]:
    """Return violation messages if point indices are not strictly increasing."""
    out: List[str] = []
    for i in range(1, len(points)):
        if points[i].index <= points[i - 1].index:
            out.append(
                f"Point indices must be strictly increasing; index[{i}]="
                f"{points[i].index} <= index[{i - 1}]={points[i - 1].index}."
            )
    return out


def _alternation(points: Sequence[WavePoint], starts_at: ExtremumType) -> List[str]:
    """Return violation messages if extrema do not alternate starting at ``starts_at``."""
    out: List[str] = []
    expected = starts_at
    other = (
        ExtremumType.VALLEY if starts_at == ExtremumType.PEAK else ExtremumType.PEAK
    )
    for i, pt in enumerate(points):
        if pt.extremum_type != expected:
            out.append(
                f"Point {i} should be {expected.value}; got {pt.extremum_type.value}."
            )
        expected = other if expected == starts_at else starts_at
    return out


# ---------------------------------------------------------------------------
# DiagonalRule
# ---------------------------------------------------------------------------


class DiagonalRule(BaseRule):
    """Validate a 5-wave Diagonal (Leading or Ending).

    Diagonals share most structural rules with impulses but:

    * Wave 4 **must** overlap Wave 1's territory (defining feature).
    * Contracting diagonals require ``|W1| > |W3| > |W5|``.
    * Expanding diagonals require ``|W1| < |W3| < |W5|``.

    Wave 2's structural alternation (valley/peak/...) still holds. Wave
    1's three core rules from :class:`ImpulseRule` are relaxed only on
    overlap.
    """

    pattern_type = PatternType.DIAGONAL
    required_points = 6  # 5 waves => 6 extrema

    def _validate(self, points: List[WavePoint]) -> WavePattern:
        violations: List[str] = []

        w1_start, w1_end = points[0], points[1]
        if w1_start.price < w1_end.price:
            direction = 1
            starts_at = ExtremumType.VALLEY
        elif w1_start.price > w1_end.price:
            direction = -1
            starts_at = ExtremumType.PEAK
        else:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=points,
                is_valid=False,
                violations=["Wave 1 has zero length."],
                direction=0,
            )

        violations.extend(_alternation(points, starts_at))
        violations.extend(_indices_strict(points))

        w1_len = _length(points[0], points[1])
        w2_len = _length(points[1], points[2])
        w3_len = _length(points[2], points[3])
        w4_len = _length(points[3], points[4])
        w5_len = _length(points[4], points[5])

        # Wave 2 must not exceed 100% of W1 (same as impulse).
        if direction == 1 and points[2].price <= w1_start.price:
            violations.append(
                f"Wave 2 retraced >=100% of Wave 1 "
                f"(W2 end={points[2].price:.4f} <= W1 start={w1_start.price:.4f})."
            )
        if direction == -1 and points[2].price >= w1_start.price:
            violations.append(
                f"Wave 2 retraced >=100% of Wave 1 "
                f"(W2 end={points[2].price:.4f} >= W1 start={w1_start.price:.4f})."
            )

        # Defining feature: Wave 4 must overlap Wave 1's territory.
        # For bullish: W4 end (valley) must be <= W1 end (peak).
        # For bearish: W4 end (peak)   must be >= W1 end (valley).
        if direction == 1 and points[4].price > points[1].price:
            violations.append(
                f"Diagonal requires W4 to overlap W1 territory "
                f"(W4 end={points[4].price:.4f} > W1 end={points[1].price:.4f})."
            )
        if direction == -1 and points[4].price < points[1].price:
            violations.append(
                f"Diagonal requires W4 to overlap W1 territory "
                f"(W4 end={points[4].price:.4f} < W1 end={points[1].price:.4f})."
            )

        # Contracting vs Expanding classification.
        contracting = w1_len > w3_len > w5_len
        expanding = w1_len < w3_len < w5_len
        sub_type = (
            "contracting" if contracting
            else "expanding" if expanding
            else "irregular"
        )
        if not contracting and not expanding:
            violations.append(
                f"Diagonal must be strictly contracting or expanding "
                f"(W1={w1_len:.4f}, W3={w3_len:.4f}, W5={w5_len:.4f})."
            )

        # Wave 3 must still not be the shortest motive wave.
        if w3_len < w1_len and w3_len < w5_len:
            violations.append(
                f"Wave 3 is the shortest motive wave "
                f"(W1={w1_len:.4f}, W3={w3_len:.4f}, W5={w5_len:.4f})."
            )

        pattern = WavePattern(
            pattern_type=self.pattern_type,
            points=points,
            is_valid=not violations,
            violations=violations,
            direction=direction,
        )
        # Stamp sub-type as the first "violation" entry on valid patterns
        # so callers (scoring engine) can read it without changing the
        # dataclass shape. Keep the field empty on invalid patterns.
        if pattern.is_valid:
            pattern.violations = [f"sub_type={sub_type}"]
            # Silence W4 and W2 lengths from feeding into the score.
            _ = (w2_len, w4_len)
        return pattern


# ---------------------------------------------------------------------------
# FlatRule
# ---------------------------------------------------------------------------


class FlatRule(BaseRule):
    """Validate an A-B-C Flat (Regular, Expanded, Running).

    A flat is a 3-3-5 corrective pattern. We validate at the wave level
    (ignoring internal sub-structure) using the price endpoints:

    * Regular:  ``B`` ends ~ at A's start (90-105% retracement).
    * Expanded: ``B`` exceeds A's start by >100% retracement; ``C``
      then exceeds B's start by >100%.
    * Running:  ``B`` exceeds A's start, but ``C`` falls short of A's
      end (weaker correction in strong trend).

    Returns a :class:`WavePattern` with the detected sub-type stamped in
    ``violations`` on success.
    """

    pattern_type = PatternType.FLAT
    required_points = 4  # 3 waves => 4 extrema

    def _validate(self, points: List[WavePoint]) -> WavePattern:
        violations: List[str] = []

        a_start, a_end, b_end, c_end = points

        if a_start.price > a_end.price:
            direction = -1  # bearish flat (down-up-down)
            starts_at = ExtremumType.PEAK
        elif a_start.price < a_end.price:
            direction = 1
            starts_at = ExtremumType.VALLEY
        else:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=points,
                is_valid=False,
                violations=["Wave A has zero length."],
                direction=0,
            )

        violations.extend(_alternation(points, starts_at))
        violations.extend(_indices_strict(points))

        a_len = _length(a_start, a_end)
        b_len = _length(a_end, b_end)
        c_len = _length(b_end, c_end)

        # B retracement % of A: how far B retraced toward (or past) A's start.
        # For a bullish flat (A up):  retracement = (a_end - b_end) / a_len.
        # For a bearish flat (A down): retracement = (b_end - a_end) / a_len.
        #
        # "C undershoots A's end" means C falls short of where A finished
        # (typical of running flats in strong parent trends). For a
        # bullish flat, A's end is the peak, so an undershoot means
        # c_end < a_end. For a bearish flat, A's end is the valley, so
        # an undershoot means c_end > a_end. (Earlier draft had the
        # inequality inverted; fixed here.)
        if direction == 1:
            b_retracement = (a_end.price - b_end.price) / a_len
            c_undershoot = c_end.price < a_end.price
        else:
            b_retracement = (b_end.price - a_end.price) / a_len
            c_undershoot = c_end.price > a_end.price

        # Classify sub-type.
        sub_type = None
        if _FLAT_REGULAR_B_LOW <= b_retracement <= _FLAT_REGULAR_B_HIGH:
            # Regular flat: C ends roughly at A's start (full retracement of B).
            sub_type = "regular"
        elif b_retracement > _FLAT_EXPANDED_B_MIN:
            # Expanded: B passes A's start; C must exceed B's reach by 100%.
            if c_len > _FLAT_EXPANDED_C_MIN * b_len:
                sub_type = "expanded"
            elif c_undershoot:
                # Running flat: B exceeded A's start (so the correction
                # had real teeth) but C fell short of A's terminus,
                # indicating a strong parent trend resuming.
                sub_type = "running"
            else:
                violations.append(
                    f"B exceeds 100% of A but C does not exceed B by >=100% "
                    f"(b_retracement={b_retracement:.3f}, c_len={c_len:.3f}, b_len={b_len:.3f})."
                )
        else:
            violations.append(
                f"Flat B retracement {b_retracement:.3f} outside regular/expanded ranges."
            )

        # Sanity: C should travel in same direction as A (correctives move
        # against the parent trend in the same direction as A by definition).
        if direction == 1 and c_end.price <= b_end.price:
            violations.append(
                f"Flat C must continue past B in A's direction "
                f"(C end={c_end.price:.4f} <= B end={b_end.price:.4f})."
            )
        if direction == -1 and c_end.price >= b_end.price:
            violations.append(
                f"Flat C must continue past B in A's direction "
                f"(C end={c_end.price:.4f} >= B end={b_end.price:.4f})."
            )

        pattern = WavePattern(
            pattern_type=self.pattern_type,
            points=points,
            is_valid=not violations,
            violations=violations,
            direction=direction,
        )
        if pattern.is_valid and sub_type is not None:
            pattern.violations = [f"sub_type={sub_type}"]
        return pattern


# ---------------------------------------------------------------------------
# TriangleRule
# ---------------------------------------------------------------------------


class TriangleRule(BaseRule):
    """Validate a 5-leg Triangle (Contracting or Expanding).

    Triangles are ``a-b-c-d-e`` 3-3-3-3-3 corrective patterns. We do
    not validate the internal sub-3s but enforce the leg-ratio rule
    against the wave endpoints:

    * Contracting: each leg's length is ~50-95% of the prior leg.
    * Expanding:   each leg's length is ~105-200% of the prior leg.

    Six extrema describe five legs.
    """

    pattern_type = PatternType.TRIANGLE
    required_points = 6  # 5 legs => 6 extrema

    def _validate(self, points: List[WavePoint]) -> WavePattern:
        violations: List[str] = []

        a_start, a_end = points[0], points[1]
        if a_start.price < a_end.price:
            direction_leg_a = 1
            starts_at = ExtremumType.VALLEY
        elif a_start.price > a_end.price:
            direction_leg_a = -1
            starts_at = ExtremumType.PEAK
        else:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=points,
                is_valid=False,
                violations=["Leg A has zero length."],
                direction=0,
            )

        violations.extend(_alternation(points, starts_at))
        violations.extend(_indices_strict(points))

        legs: List[float] = []
        for i in range(len(points) - 1):
            legs.append(_length(points[i], points[i + 1]))

        if any(l == 0 for l in legs):
            violations.append("Triangle has a zero-length leg.")

        # Compute per-leg ratios vs previous leg.
        ratios: List[float] = []
        if all(l > 0 for l in legs):
            for i in range(1, len(legs)):
                ratios.append(legs[i] / legs[i - 1])

        contracting = all(_TRIANGLE_CONTRACTING_LOW <= r <= _TRIANGLE_CONTRACTING_HIGH for r in ratios)
        expanding = all(_TRIANGLE_EXPANDING_LOW <= r <= _TRIANGLE_EXPANDING_HIGH for r in ratios)

        if contracting and not expanding:
            sub_type = "contracting"
        elif expanding and not contracting:
            sub_type = "expanding"
        else:
            sub_type = "irregular"
            violations.append(
                f"Triangle leg ratios do not match contracting or expanding bounds "
                f"(ratios={[round(r, 3) for r in ratios]})."
            )

        pattern = WavePattern(
            pattern_type=self.pattern_type,
            points=points,
            is_valid=not violations,
            violations=violations,
            direction=direction_leg_a,
        )
        if pattern.is_valid:
            pattern.violations = [f"sub_type={sub_type}"]
        return pattern


__all__ = [
    "DiagonalRule",
    "FlatRule",
    "TriangleRule",
]
