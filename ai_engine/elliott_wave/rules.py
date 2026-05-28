"""Elliott Wave rule engine.

Wave 1 ships the two foundational rule sets:

* :class:`ImpulseRule` — validates 1-5 motive waves against the three
  non-negotiable Elliott rules:
    1. Wave 2 cannot retrace more than 100% of Wave 1.
    2. Wave 3 cannot be the shortest of the motive waves (1, 3, 5).
    3. Wave 4 cannot overlap the price territory of Wave 1.

* :class:`ZigzagRule` — validates A-B-C corrective patterns:
    1. Wave B cannot retrace more than (or equal to) 100% of Wave A.
    2. Wave C usually extends beyond the end of Wave A (i.e. C goes past
       A's terminal price).

The :class:`RuleEngine` walks a sorted sequence of extrema and emits all
candidate patterns that satisfy these rules. Fibonacci scoring and the
remaining EWT pattern families (Flats, Triangles, Diagonals, Complex
W-X-Y) belong to Wave 2 and are intentionally out of scope here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    WavePattern,
    WavePoint,
)


# Number of points that define each supported pattern.
_IMPULSE_POINTS = 6  # 5 waves => 6 extrema
_ZIGZAG_POINTS = 4  # 3 waves => 4 extrema


# ---------------------------------------------------------------------------
# BaseRule
# ---------------------------------------------------------------------------


class BaseRule(ABC):
    """Abstract Elliott Wave rule.

    Concrete subclasses inspect a sequence of :class:`WavePoint` and
    return a :class:`WavePattern` reporting validity and any rule
    violations.

    Subclasses must define:
        * :attr:`pattern_type`: the :class:`PatternType` they recognise.
        * :attr:`required_points`: how many extrema they consume.
        * :meth:`_validate`: the actual rule check.
    """

    pattern_type: PatternType = PatternType.NONE
    required_points: int = 0

    def validate(self, points: Sequence[WavePoint]) -> WavePattern:
        """Validate a candidate sequence and return a :class:`WavePattern`."""
        if len(points) != self.required_points:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=list(points),
                is_valid=False,
                violations=[
                    f"Expected {self.required_points} points for {self.pattern_type.value}; "
                    f"got {len(points)}."
                ],
                direction=0,
            )
        return self._validate(list(points))

    @abstractmethod
    def _validate(self, points: List[WavePoint]) -> WavePattern:
        """Subclass hook — assume ``len(points) == self.required_points``."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# ImpulseRule (1-5)
# ---------------------------------------------------------------------------


class ImpulseRule(BaseRule):
    """Validate a 5-wave Impulse against Elliott's three core rules.

    An Impulse is described by **six** :class:`WavePoint`s: ``P0..P5``
    where the waves are ``P0->P1`` (Wave 1), ``P1->P2`` (Wave 2),
    ``P2->P3`` (Wave 3), ``P3->P4`` (Wave 4), ``P4->P5`` (Wave 5).

    A bullish impulse starts at a valley and ends at a peak after
    alternating valley/peak/valley/peak/valley/peak. The bearish
    impulse is the mirror.
    """

    pattern_type = PatternType.IMPULSE
    required_points = _IMPULSE_POINTS

    def _validate(self, points: List[WavePoint]) -> WavePattern:
        violations: List[str] = []

        # Determine direction from W1.
        w1_start, w1_end = points[0], points[1]
        if w1_start.price < w1_end.price:
            direction = 1  # bullish
            expected = [
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
            ]
        elif w1_start.price > w1_end.price:
            direction = -1  # bearish
            expected = [
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
            ]
        else:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=points,
                is_valid=False,
                violations=["Wave 1 has zero length."],
                direction=0,
            )

        # Structural alternation check.
        for i, (pt, exp) in enumerate(zip(points, expected)):
            if pt.extremum_type != exp:
                violations.append(
                    f"Point {i} should be {exp.value} for direction={direction}; "
                    f"got {pt.extremum_type.value}."
                )

        # Strictly monotonically increasing indices.
        for i in range(1, len(points)):
            if points[i].index <= points[i - 1].index:
                violations.append(
                    f"Point indices must be strictly increasing; index[{i}]="
                    f"{points[i].index} <= index[{i - 1}]={points[i - 1].index}."
                )

        w1 = (points[0], points[1])
        w2 = (points[1], points[2])
        w3 = (points[2], points[3])
        w4 = (points[3], points[4])
        w5 = (points[4], points[5])

        def length(seg: Tuple[WavePoint, WavePoint]) -> float:
            return abs(seg[1].price - seg[0].price)

        w1_len = length(w1)
        w3_len = length(w3)
        w5_len = length(w5)

        # Rule 1: Wave 2 cannot retrace more than 100% of Wave 1.
        # For a bullish impulse, that means W2 low must be > W1 start (valley).
        # For a bearish impulse, W2 high must be < W1 start (peak).
        if direction == 1:
            if w2[1].price <= w1[0].price:
                violations.append(
                    f"Rule 1: Wave 2 retraced >=100% of Wave 1 "
                    f"(W2 end={w2[1].price:.4f} <= W1 start={w1[0].price:.4f})."
                )
        else:
            if w2[1].price >= w1[0].price:
                violations.append(
                    f"Rule 1: Wave 2 retraced >=100% of Wave 1 "
                    f"(W2 end={w2[1].price:.4f} >= W1 start={w1[0].price:.4f})."
                )

        # Rule 2: Wave 3 cannot be the shortest among the three motive waves.
        if w3_len < w1_len and w3_len < w5_len:
            violations.append(
                f"Rule 2: Wave 3 is the shortest motive wave "
                f"(W1={w1_len:.4f}, W3={w3_len:.4f}, W5={w5_len:.4f})."
            )

        # Rule 3: Wave 4 cannot overlap the price territory of Wave 1.
        # Bullish: W4 low (w4 end, a valley) must stay above W1 end (peak).
        # Bearish: W4 high (w4 end, a peak) must stay below W1 end (valley).
        if direction == 1:
            if w4[1].price <= w1[1].price:
                violations.append(
                    f"Rule 3: Wave 4 overlaps Wave 1 territory "
                    f"(W4 end={w4[1].price:.4f} <= W1 end={w1[1].price:.4f})."
                )
        else:
            if w4[1].price >= w1[1].price:
                violations.append(
                    f"Rule 3: Wave 4 overlaps Wave 1 territory "
                    f"(W4 end={w4[1].price:.4f} >= W1 end={w1[1].price:.4f})."
                )

        return WavePattern(
            pattern_type=self.pattern_type,
            points=points,
            is_valid=not violations,
            violations=violations,
            direction=direction,
        )


# ---------------------------------------------------------------------------
# ZigzagRule (A-B-C)
# ---------------------------------------------------------------------------


class ZigzagRule(BaseRule):
    """Validate a corrective A-B-C Zigzag.

    A zigzag is described by **four** :class:`WavePoint`s: ``P0..P3``
    where the waves are ``P0->P1`` (Wave A), ``P1->P2`` (Wave B),
    ``P2->P3`` (Wave C).

    Bearish (down-up-down): starts at peak. Bullish (up-down-up): starts
    at valley. (Counter-trend; orientation depends on the parent trend.)
    """

    pattern_type = PatternType.ZIGZAG
    required_points = _ZIGZAG_POINTS

    def _validate(self, points: List[WavePoint]) -> WavePattern:
        violations: List[str] = []

        a_start, a_end = points[0], points[1]
        b_end = points[2]
        c_end = points[3]

        if a_start.price > a_end.price:
            direction = -1  # bearish zigzag (down-up-down)
            expected = [
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
            ]
        elif a_start.price < a_end.price:
            direction = 1  # bullish zigzag (up-down-up)
            expected = [
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
                ExtremumType.VALLEY,
                ExtremumType.PEAK,
            ]
        else:
            return WavePattern(
                pattern_type=self.pattern_type,
                points=points,
                is_valid=False,
                violations=["Wave A has zero length."],
                direction=0,
            )

        for i, (pt, exp) in enumerate(zip(points, expected)):
            if pt.extremum_type != exp:
                violations.append(
                    f"Point {i} should be {exp.value} for direction={direction}; "
                    f"got {pt.extremum_type.value}."
                )

        for i in range(1, len(points)):
            if points[i].index <= points[i - 1].index:
                violations.append(
                    f"Point indices must be strictly increasing; index[{i}]="
                    f"{points[i].index} <= index[{i - 1}]={points[i - 1].index}."
                )

        # Rule 1: B retraces less than 100% of A — i.e. B does not pass
        # A's starting price. Bearish: b_end < a_start (peak). Bullish:
        # b_end > a_start (valley).
        if direction == -1:
            if b_end.price >= a_start.price:
                violations.append(
                    f"Rule 1: Wave B retraced >=100% of Wave A "
                    f"(B end={b_end.price:.4f} >= A start={a_start.price:.4f})."
                )
        else:
            if b_end.price <= a_start.price:
                violations.append(
                    f"Rule 1: Wave B retraced >=100% of Wave A "
                    f"(B end={b_end.price:.4f} <= A start={a_start.price:.4f})."
                )

        # Rule 2: C usually goes beyond the end of A.
        # Bearish: c_end <= a_end (valley) — i.e. C closes lower than A's low.
        # Bullish: c_end >= a_end (peak) — i.e. C closes higher than A's high.
        if direction == -1:
            if c_end.price > a_end.price:
                violations.append(
                    f"Rule 2: Wave C did not extend beyond Wave A "
                    f"(C end={c_end.price:.4f} > A end={a_end.price:.4f})."
                )
        else:
            if c_end.price < a_end.price:
                violations.append(
                    f"Rule 2: Wave C did not extend beyond Wave A "
                    f"(C end={c_end.price:.4f} < A end={a_end.price:.4f})."
                )

        return WavePattern(
            pattern_type=self.pattern_type,
            points=points,
            is_valid=not violations,
            violations=violations,
            direction=direction,
        )


# ---------------------------------------------------------------------------
# RuleEngine
# ---------------------------------------------------------------------------


@dataclass
class RuleEngine:
    """Walk a sequence of extrema and emit all valid patterns.

    The engine slides a window over the extrema list and feeds each
    candidate window to every registered rule. Only patterns whose
    :attr:`WavePattern.is_valid` is True are returned, except when
    ``include_invalid`` is set — useful for diagnostics.
    """

    rules: Optional[List[BaseRule]] = None
    include_invalid: bool = False

    def __post_init__(self) -> None:
        if self.rules is None:
            # Import locally to avoid an import cycle with advanced_rules
            # (which imports BaseRule from this module).
            from ai_engine.elliott_wave.advanced_rules import (
                DiagonalRule,
                FlatRule,
                TriangleRule,
            )

            self.rules = [
                ImpulseRule(),
                ZigzagRule(),
                DiagonalRule(),
                FlatRule(),
                TriangleRule(),
            ]

    def validate(self, points: Sequence[WavePoint]) -> List[WavePattern]:
        """Return every valid pattern detectable in ``points``.

        Candidate windows are consecutive sub-sequences sized to each
        rule's :attr:`required_points`. Overlapping matches are allowed
        — the scoring engine in Wave 2 will deduplicate via Fibonacci
        confluence.
        """
        results: List[WavePattern] = []
        pts = list(points)
        n = len(pts)
        for rule in self.rules or ():
            size = rule.required_points
            if size <= 0 or n < size:
                continue
            for start in range(0, n - size + 1):
                candidate = pts[start : start + size]
                pattern = rule.validate(candidate)
                if pattern.is_valid or self.include_invalid:
                    results.append(pattern)
        return results

    def validate_one(self, points: Sequence[WavePoint], pattern_type: PatternType) -> WavePattern:
        """Validate exactly one explicit candidate against the matching rule.

        Useful for tests and for the future scoring engine which already
        knows the candidate's pattern type.
        """
        for rule in self.rules or ():
            if rule.pattern_type == pattern_type:
                return rule.validate(points)
        raise KeyError(f"No registered rule for pattern_type={pattern_type.value}")


__all__ = [
    "BaseRule",
    "ImpulseRule",
    "RuleEngine",
    "ZigzagRule",
]
