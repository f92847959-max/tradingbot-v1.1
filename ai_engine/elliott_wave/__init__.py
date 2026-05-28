"""Elliott Wave Theory integration package.

Provides automated wave counting, rule-based validation, and feature
engineering primitives for the GoldBot 2 trading engine.

Wave 1 surface:
    - models: WavePoint, Wave, WavePattern dataclasses
    - detector: find_extrema, calculate_ewo, WaveDetector
    - rules: BaseRule, ImpulseRule, ZigzagRule, RuleEngine

Wave 2 surface (Phase 14-02):
    - fibonacci: calculate_retracement, calculate_projection, get_wave_targets
    - advanced_rules: DiagonalRule, FlatRule, TriangleRule
    - scoring: score_pattern, get_primary_count

Wave 3 (system integration / ML) is implemented in 14-03.
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
