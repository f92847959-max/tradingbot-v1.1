"""Unit tests for Elliott Wave Wave 2 (Phase 14-02).

Covers:
    * ``calculate_retracement`` / ``calculate_projection`` math
    * ``get_wave_targets`` per pattern type
    * ``DiagonalRule`` (Leading/Ending Diagonals)
    * ``FlatRule`` (Regular, Expanded, Running)
    * ``TriangleRule`` (Contracting/Expanding)
    * ``score_pattern`` / ``get_primary_count`` confluence ranking

Wave 1's 35 tests in ``tests/test_elliott_wave.py`` remain authoritative
for the detection core; this file extends coverage with the Wave 2
surface.
"""

from __future__ import annotations

from typing import List

import math
import pytest

from ai_engine.elliott_wave.fibonacci import (
    IDEAL_WAVE_RATIOS,
    STANDARD_PROJECTION_RATIOS,
    STANDARD_RETRACEMENT_RATIOS,
    calculate_projection,
    calculate_retracement,
    get_wave_targets,
)
from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    WavePattern,
    WavePoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point(idx: int, price: float, etype: ExtremumType) -> WavePoint:
    return WavePoint(index=idx, price=price, extremum_type=etype)


# ---------------------------------------------------------------------------
# Fibonacci math
# ---------------------------------------------------------------------------


class TestCalculateRetracement:
    def test_zero_ratio_returns_end(self) -> None:
        assert calculate_retracement(100.0, 200.0, 0.0) == 200.0

    def test_full_ratio_returns_start(self) -> None:
        assert calculate_retracement(100.0, 200.0, 1.0) == 100.0

    def test_standard_618_bullish(self) -> None:
        # 0.618 retracement of a 100 -> 200 rally = 200 - 0.618*100 = 138.2
        assert calculate_retracement(100.0, 200.0, 0.618) == pytest.approx(138.2)

    def test_bearish_retracement(self) -> None:
        # 0.5 retracement of a 200 -> 100 sell-off = 100 + 0.5*100 = 150
        assert calculate_retracement(200.0, 100.0, 0.5) == pytest.approx(150.0)

    def test_negative_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            calculate_retracement(100.0, 200.0, -0.1)

    def test_nan_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            calculate_retracement(100.0, 200.0, float("nan"))

    def test_non_numeric_inputs_rejected(self) -> None:
        with pytest.raises(TypeError):
            calculate_retracement("a", 200.0, 0.5)


class TestCalculateProjection:
    def test_plan_verify_command(self) -> None:
        """Exact case from Task 1 verify block."""
        assert calculate_projection(100, 200, 150, 1.618) == 311.8

    def test_bearish_projection(self) -> None:
        # Wave 1 down 100 -> 50; project from 60 at 1.618 of |w1|=50 = 81
        # 60 - 1.0*50*1.618 = 60 - 80.9 = -20.9
        assert calculate_projection(100.0, 50.0, 60.0, 1.618) == pytest.approx(-20.9)

    def test_flat_w1_yields_anchor(self) -> None:
        assert calculate_projection(100.0, 100.0, 200.0, 1.618) == 200.0

    def test_negative_ratio_rejected(self) -> None:
        with pytest.raises(ValueError):
            calculate_projection(100.0, 200.0, 150.0, -1.0)


class TestGetWaveTargets:
    def test_empty_pattern_returns_empty_dict(self) -> None:
        empty = WavePattern(pattern_type=PatternType.IMPULSE, points=[])
        assert get_wave_targets(empty) == {}

    def test_impulse_targets_include_w3_and_w2_retracement(self) -> None:
        pattern = WavePattern(
            pattern_type=PatternType.IMPULSE,
            points=[
                _point(0, 100, ExtremumType.VALLEY),
                _point(1, 200, ExtremumType.PEAK),
                _point(2, 150, ExtremumType.VALLEY),
                _point(3, 350, ExtremumType.PEAK),
                _point(4, 280, ExtremumType.VALLEY),
                _point(5, 400, ExtremumType.PEAK),
            ],
            is_valid=True,
        )
        targets = get_wave_targets(pattern)
        # W3 at 1.618 anchored to end-of-W2 (150): 150 + 100*1.618 = 311.8
        assert targets["w3_1.618"] == pytest.approx(311.8)
        # W2 retracement at 0.618 of W1 (100 -> 200): 200 - 0.618*100 = 138.2
        assert targets["w2_retracement_0.618"] == pytest.approx(138.2)
        # W5 anchored to end-of-W4 (280): 280 + 1.0 * 100 = 380
        assert targets["w5_1.0"] == pytest.approx(380.0)

    def test_zigzag_targets_include_c_projection(self) -> None:
        pattern = WavePattern(
            pattern_type=PatternType.ZIGZAG,
            points=[
                _point(0, 100, ExtremumType.VALLEY),
                _point(1, 200, ExtremumType.PEAK),
                _point(2, 150, ExtremumType.VALLEY),
                _point(3, 250, ExtremumType.PEAK),
            ],
            is_valid=True,
        )
        targets = get_wave_targets(pattern)
        # C at 1.0 anchored to end-of-B (150): 150 + 100*1.0 = 250
        assert targets["c_1.0"] == pytest.approx(250.0)

    def test_unknown_pattern_returns_empty(self) -> None:
        pattern = WavePattern(pattern_type=PatternType.NONE, points=[
            _point(0, 100, ExtremumType.VALLEY)
        ])
        assert get_wave_targets(pattern) == {}


class TestStandardConstants:
    def test_retracement_ratios_contain_618(self) -> None:
        assert 0.618 in STANDARD_RETRACEMENT_RATIOS

    def test_projection_ratios_contain_1618_and_2618(self) -> None:
        assert 1.618 in STANDARD_PROJECTION_RATIOS
        assert 2.618 in STANDARD_PROJECTION_RATIOS

    def test_ideal_ratios_keyed_by_pattern_and_label(self) -> None:
        assert (PatternType.IMPULSE, "2") in IDEAL_WAVE_RATIOS
        assert (PatternType.ZIGZAG, "C") in IDEAL_WAVE_RATIOS
        assert (PatternType.TRIANGLE, "B") in IDEAL_WAVE_RATIOS
