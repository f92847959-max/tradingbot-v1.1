"""Elliott Wave Theory integration package.

Provides automated wave counting, rule-based validation, and feature
engineering primitives for the GoldBot 2 trading engine.

Wave 1 surface (this module set):
    - models: WavePoint, Wave, WavePattern dataclasses
    - detector: find_extrema, calculate_ewo, WaveDetector
    - rules: BaseRule, ImpulseRule, ZigzagRule, RuleEngine

Waves 2 (Fibonacci + advanced patterns) and 3 (system integration / ML)
are implemented in subsequent plans.
"""

from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    Wave,
    WavePattern,
    WavePoint,
)

__all__ = [
    "ExtremumType",
    "PatternType",
    "Wave",
    "WavePattern",
    "WavePoint",
]
