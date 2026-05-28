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

from ai_engine.elliott_wave.advanced_rules import (
    DiagonalRule,
    FlatRule,
    TriangleRule,
)
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
from ai_engine.elliott_wave.rules import RuleEngine
from ai_engine.elliott_wave.scoring import (
    get_primary_count,
    rank_patterns,
    score_pattern,
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


# ---------------------------------------------------------------------------
# DiagonalRule
# ---------------------------------------------------------------------------


def _contracting_bullish_diagonal() -> List[WavePoint]:
    """Five-wave bullish diagonal, contracting, with W4 overlapping W1."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),  # W1 start
        _point(10, 130.0, ExtremumType.PEAK),   # W1 end (len 30)
        _point(20, 115.0, ExtremumType.VALLEY), # W2 end (50% retrace, above start)
        _point(30, 140.0, ExtremumType.PEAK),   # W3 end (len 25 < W1)
        _point(40, 125.0, ExtremumType.VALLEY), # W4 end -- OVERLAPS W1 (<130 peak)
        _point(50, 145.0, ExtremumType.PEAK),   # W5 end (len 20 < W3)
    ]


def _impulse_via_diagonal_points() -> List[WavePoint]:
    """Same 6 points as a valid impulse — should fail DiagonalRule (no overlap)."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 120.0, ExtremumType.PEAK),
        _point(20, 110.0, ExtremumType.VALLEY),
        _point(30, 150.0, ExtremumType.PEAK),
        _point(40, 135.0, ExtremumType.VALLEY),  # 135 > 120 peak -> NO overlap
        _point(50, 160.0, ExtremumType.PEAK),
    ]


class TestDiagonalRule:
    def test_valid_contracting_bullish_diagonal(self) -> None:
        result = DiagonalRule().validate(_contracting_bullish_diagonal())
        assert result.is_valid, result.violations
        assert result.direction == 1
        assert any("sub_type=contracting" in v for v in result.violations)

    def test_diagonal_rejects_non_overlapping_w4(self) -> None:
        result = DiagonalRule().validate(_impulse_via_diagonal_points())
        assert not result.is_valid
        assert any("overlap" in v.lower() for v in result.violations)

    def test_diagonal_rejects_wrong_point_count(self) -> None:
        pts = _contracting_bullish_diagonal()[:4]
        result = DiagonalRule().validate(pts)
        assert not result.is_valid
        assert any("Expected 6 points" in v for v in result.violations)

    def test_diagonal_zero_w1_is_invalid(self) -> None:
        pts = _contracting_bullish_diagonal()
        pts[1] = _point(10, pts[0].price, ExtremumType.PEAK)
        result = DiagonalRule().validate(pts)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# FlatRule
# ---------------------------------------------------------------------------


def _regular_bullish_flat() -> List[WavePoint]:
    """Regular flat in a bullish counter-trend correction (A up, B down to start, C up to ~A end)."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),  # A start
        _point(10, 120.0, ExtremumType.PEAK),   # A end (up 20)
        _point(20, 101.0, ExtremumType.VALLEY), # B end (~95% retrace -> regular)
        _point(30, 119.5, ExtremumType.PEAK),   # C end (~A end)
    ]


def _expanded_bullish_flat() -> List[WavePoint]:
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 120.0, ExtremumType.PEAK),   # A end (len 20)
        _point(20, 96.0, ExtremumType.VALLEY),  # B end (retrace 24/20 = 1.2 > 1.0)
        _point(30, 150.0, ExtremumType.PEAK),   # C end (len 54 > b_len 24)
    ]


class TestFlatRule:
    def test_valid_regular_flat(self) -> None:
        result = FlatRule().validate(_regular_bullish_flat())
        assert result.is_valid, result.violations
        assert result.direction == 1
        assert any("sub_type=regular" in v for v in result.violations)

    def test_valid_expanded_flat(self) -> None:
        result = FlatRule().validate(_expanded_bullish_flat())
        assert result.is_valid, result.violations
        assert any("sub_type=expanded" in v for v in result.violations)

    def test_flat_zero_a_is_invalid(self) -> None:
        pts = _regular_bullish_flat()
        pts[1] = _point(10, pts[0].price, ExtremumType.PEAK)
        result = FlatRule().validate(pts)
        assert not result.is_valid

    def test_flat_wrong_point_count(self) -> None:
        result = FlatRule().validate(_regular_bullish_flat()[:3])
        assert not result.is_valid


# ---------------------------------------------------------------------------
# TriangleRule
# ---------------------------------------------------------------------------


def _contracting_triangle() -> List[WavePoint]:
    """Contracting triangle: each leg ~70-80% of the previous."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 120.0, ExtremumType.PEAK),   # leg a (len 20)
        _point(20, 104.0, ExtremumType.VALLEY), # leg b (len 16, 80%)
        _point(30, 116.5, ExtremumType.PEAK),   # leg c (len 12.5, ~78%)
        _point(40, 107.0, ExtremumType.VALLEY), # leg d (len 9.5, 76%)
        _point(50, 114.0, ExtremumType.PEAK),   # leg e (len 7.0, ~74%)
    ]


def _expanding_triangle() -> List[WavePoint]:
    """Expanding triangle: each leg ~130% of previous."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 110.0, ExtremumType.PEAK),   # leg a (len 10)
        _point(20, 96.0, ExtremumType.VALLEY),  # leg b (len 14, 140%)
        _point(30, 116.0, ExtremumType.PEAK),   # leg c (len 20, ~143%)
        _point(40, 87.0, ExtremumType.VALLEY),  # leg d (len 29, 145%)
        _point(50, 125.0, ExtremumType.PEAK),   # leg e (len 38, ~131%)
    ]


class TestTriangleRule:
    def test_valid_contracting_triangle(self) -> None:
        result = TriangleRule().validate(_contracting_triangle())
        assert result.is_valid, result.violations
        assert any("sub_type=contracting" in v for v in result.violations)

    def test_valid_expanding_triangle(self) -> None:
        result = TriangleRule().validate(_expanding_triangle())
        assert result.is_valid, result.violations
        assert any("sub_type=expanding" in v for v in result.violations)

    def test_triangle_rejects_impulse_shape(self) -> None:
        # Same point count as triangle but with diverging non-ratio legs
        # — should fail the ratio bounds.
        points = [
            _point(0, 100.0, ExtremumType.VALLEY),
            _point(10, 120.0, ExtremumType.PEAK),
            _point(20, 110.0, ExtremumType.VALLEY),
            _point(30, 200.0, ExtremumType.PEAK),  # leg c way too long (900% of leg b)
            _point(40, 130.0, ExtremumType.VALLEY),
            _point(50, 160.0, ExtremumType.PEAK),
        ]
        result = TriangleRule().validate(points)
        assert not result.is_valid


# ---------------------------------------------------------------------------
# RuleEngine integration: advanced rules registered by default
# ---------------------------------------------------------------------------


class TestRuleEngineWithAdvancedRules:
    def test_default_engine_registers_five_rules(self) -> None:
        eng = RuleEngine()
        names = {type(r).__name__ for r in eng.rules}
        assert names == {
            "ImpulseRule",
            "ZigzagRule",
            "DiagonalRule",
            "FlatRule",
            "TriangleRule",
        }

    def test_diagonal_detected_in_full_engine(self) -> None:
        eng = RuleEngine()
        results = eng.validate(_contracting_bullish_diagonal())
        types = {p.pattern_type for p in results}
        assert PatternType.DIAGONAL in types

    def test_triangle_detected_in_full_engine(self) -> None:
        eng = RuleEngine()
        results = eng.validate(_contracting_triangle())
        types = {p.pattern_type for p in results}
        assert PatternType.TRIANGLE in types


# ---------------------------------------------------------------------------
# Scoring engine
# ---------------------------------------------------------------------------


def _ideal_bullish_impulse() -> List[WavePoint]:
    """Impulse with ratios close to canonical: W2=61.8% W1, W3=1.618 W1,
    W4=38.2% W3, W5 = W1."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),  # W1 start
        _point(10, 200.0, ExtremumType.PEAK),   # W1 end (len 100)
        _point(20, 138.2, ExtremumType.VALLEY), # W2 end (61.8% retrace -> ideal)
        _point(30, 300.0, ExtremumType.PEAK),   # W3 end (len 161.8 -> 1.618 ideal)
        _point(40, 238.2, ExtremumType.VALLEY), # W4 end (38.2% of W3 retrace)
        _point(50, 338.2, ExtremumType.PEAK),   # W5 end (len 100 = W1)
    ]


def _weak_bullish_impulse() -> List[WavePoint]:
    """Same structure but ratios far from ideal (W3 only 1.05x W1, W5 0.3x W1)."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 200.0, ExtremumType.PEAK),   # W1 len 100
        _point(20, 195.0, ExtremumType.VALLEY), # W2 only 5% retrace (far below 0.382 ideal)
        _point(30, 300.0, ExtremumType.PEAK),   # W3 only 1.05x W1
        _point(40, 285.0, ExtremumType.VALLEY), # W4 small retrace, no overlap
        _point(50, 315.0, ExtremumType.PEAK),   # W5 only 0.3 x W1
    ]


class TestScorePattern:
    def test_invalid_pattern_scores_zero(self) -> None:
        pattern = WavePattern(
            pattern_type=PatternType.IMPULSE,
            points=[_point(0, 100, ExtremumType.VALLEY)],
            is_valid=False,
            violations=["bad shape"],
        )
        assert score_pattern(pattern) == 0.0

    def test_none_pattern_scores_zero(self) -> None:
        assert score_pattern(None) == 0.0  # type: ignore[arg-type]

    def test_ideal_impulse_scores_higher_than_weak(self) -> None:
        from ai_engine.elliott_wave.rules import ImpulseRule

        ideal = ImpulseRule().validate(_ideal_bullish_impulse())
        weak = ImpulseRule().validate(_weak_bullish_impulse())
        assert ideal.is_valid, ideal.violations
        assert weak.is_valid, weak.violations
        s_ideal = score_pattern(ideal)
        s_weak = score_pattern(weak)
        assert s_ideal > s_weak
        assert s_ideal > 0.5  # canonical ratios should rate well
        assert 0.0 <= s_weak <= s_ideal

    def test_score_in_unit_interval(self) -> None:
        from ai_engine.elliott_wave.rules import ImpulseRule

        result = ImpulseRule().validate(_ideal_bullish_impulse())
        s = score_pattern(result)
        assert 0.0 <= s <= 1.0


class TestRankAndPrimaryCount:
    def test_empty_input_returns_none(self) -> None:
        assert get_primary_count([]) is None
        assert rank_patterns([]) == []

    def test_primary_count_picks_highest(self) -> None:
        from ai_engine.elliott_wave.rules import ImpulseRule

        ideal = ImpulseRule().validate(_ideal_bullish_impulse())
        weak = ImpulseRule().validate(_weak_bullish_impulse())
        primary = get_primary_count([weak, ideal])
        assert primary is ideal

    def test_only_invalid_returns_none(self) -> None:
        bad = WavePattern(
            pattern_type=PatternType.IMPULSE,
            points=[_point(0, 100, ExtremumType.VALLEY)],
            is_valid=False,
            violations=["bad"],
        )
        assert get_primary_count([bad]) is None

    def test_rank_is_descending_by_score(self) -> None:
        from ai_engine.elliott_wave.rules import ImpulseRule

        ideal = ImpulseRule().validate(_ideal_bullish_impulse())
        weak = ImpulseRule().validate(_weak_bullish_impulse())
        ranked = rank_patterns([weak, ideal])
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True)
        assert ranked[0][0] is ideal


class TestScoringSecurityHardening:
    """T-14-04: scoring must not accept caller-supplied ratio overrides."""

    def test_score_pattern_signature_takes_only_pattern(self) -> None:
        import inspect

        sig = inspect.signature(score_pattern)
        # Only one parameter: the pattern itself.
        assert list(sig.parameters.keys()) == ["pattern"]
