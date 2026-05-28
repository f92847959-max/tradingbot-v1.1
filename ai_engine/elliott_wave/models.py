"""Data models for Elliott Wave detection.

These dataclasses describe the structural primitives shared across the
detector, rule engine, and downstream feature engineering layers.

Wave 1 scope keeps the surface minimal — Fibonacci scoring and complex
pattern metadata are introduced in Wave 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ExtremumType(str, Enum):
    """Type of local extremum identified in a price series."""

    PEAK = "peak"
    VALLEY = "valley"


class PatternType(str, Enum):
    """Elliott Wave pattern categories.

    Wave 1 only formally validates IMPULSE and ZIGZAG; the remaining
    members are placeholders so downstream consumers can switch on a
    stable enum once Wave 2 / 3 ships.
    """

    NONE = "none"
    IMPULSE = "impulse"
    ZIGZAG = "zigzag"
    FLAT = "flat"
    TRIANGLE = "triangle"
    DIAGONAL = "diagonal"
    COMPLEX = "complex"


@dataclass(frozen=True)
class WavePoint:
    """A single labelled extremum (peak or valley) in a price series.

    Attributes:
        index: Positional index in the source OHLCV frame.
        price: Price at the extremum.
        extremum_type: Whether the point is a peak or a valley.
        timestamp: Optional ISO timestamp / datetime — preserved for
            downstream logging; not used by the rule engine.
    """

    index: int
    price: float
    extremum_type: ExtremumType
    timestamp: Optional[str] = None


@dataclass
class Wave:
    """A single labelled wave between two extrema.

    Example: Wave 1 of an Impulse runs from a valley to a peak in a
    bullish 5-wave count.
    """

    label: str  # e.g. "1", "2", "3", "4", "5", "A", "B", "C"
    start: WavePoint
    end: WavePoint

    @property
    def length(self) -> float:
        """Absolute price travel of the wave."""
        return abs(self.end.price - self.start.price)

    @property
    def direction(self) -> int:
        """+1 if rising, -1 if falling, 0 if flat."""
        delta = self.end.price - self.start.price
        if delta > 0:
            return 1
        if delta < 0:
            return -1
        return 0


@dataclass
class WavePattern:
    """A candidate Elliott Wave pattern validated (or not) by the rule engine.

    Wave 1 surface intentionally omits Fibonacci scoring fields — those
    are added in Wave 2 via a subclass or extension to keep concerns
    isolated.
    """

    pattern_type: PatternType
    points: List[WavePoint]
    is_valid: bool = False
    violations: List[str] = field(default_factory=list)
    # Direction of the pattern: +1 bullish, -1 bearish, 0 unknown.
    direction: int = 0

    @property
    def waves(self) -> List[Wave]:
        """Derive Wave segments from consecutive pattern points."""
        out: List[Wave] = []
        labels = self._labels_for_pattern()
        for i in range(len(self.points) - 1):
            label = labels[i] if i < len(labels) else str(i + 1)
            out.append(Wave(label=label, start=self.points[i], end=self.points[i + 1]))
        return out

    def _labels_for_pattern(self) -> List[str]:
        """Return the canonical wave labels for this pattern type."""
        if self.pattern_type == PatternType.IMPULSE:
            return ["1", "2", "3", "4", "5"]
        if self.pattern_type == PatternType.ZIGZAG:
            return ["A", "B", "C"]
        # Fallback labelling for unsupported / future pattern types.
        return [str(i + 1) for i in range(max(0, len(self.points) - 1))]
