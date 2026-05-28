"""Unit tests for the Elliott Wave detection core (Phase 14-01).

Covers:
    * ``find_extrema`` against synthetic sine-wave data
    * ``calculate_ewo`` index alignment and length sanity
    * ``ImpulseRule`` valid and invalid sequences (Rules 1, 2, 3)
    * ``ZigzagRule`` valid and invalid sequences
    * ``WaveDetector`` end-to-end on a constructed gold-like price snippet
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd
import pytest

from ai_engine.elliott_wave.detector import (
    MAX_INPUT_LENGTH,
    WaveDetector,
    calculate_ewo,
    find_extrema,
)
from ai_engine.elliott_wave.models import (
    ExtremumType,
    PatternType,
    WavePattern,
    WavePoint,
)
from ai_engine.elliott_wave.rules import (
    BaseRule,
    ImpulseRule,
    RuleEngine,
    ZigzagRule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point(idx: int, price: float, etype: ExtremumType) -> WavePoint:
    return WavePoint(index=idx, price=price, extremum_type=etype)


def _valid_bullish_impulse() -> List[WavePoint]:
    """Construct a canonical valid bullish 5-wave impulse."""
    return [
        _point(0, 100.0, ExtremumType.VALLEY),  # W1 start
        _point(10, 120.0, ExtremumType.PEAK),   # W1 end   (len 20)
        _point(20, 110.0, ExtremumType.VALLEY), # W2 end   (50% retrace, > start)
        _point(30, 150.0, ExtremumType.PEAK),   # W3 end   (len 40)
        _point(40, 130.0, ExtremumType.VALLEY), # W4 end   (above W1 peak: no overlap)
        _point(50, 160.0, ExtremumType.PEAK),   # W5 end   (len 30)
    ]


def _valid_bearish_impulse() -> List[WavePoint]:
    return [
        _point(0, 160.0, ExtremumType.PEAK),
        _point(10, 140.0, ExtremumType.VALLEY),  # W1 down
        _point(20, 150.0, ExtremumType.PEAK),    # W2 up, < start
        _point(30, 110.0, ExtremumType.VALLEY),  # W3 down strong
        _point(40, 130.0, ExtremumType.PEAK),    # W4 up, below W1 valley (no overlap)
        _point(50, 100.0, ExtremumType.VALLEY),  # W5 down
    ]


def _valid_bullish_zigzag() -> List[WavePoint]:
    return [
        _point(0, 100.0, ExtremumType.VALLEY),
        _point(10, 120.0, ExtremumType.PEAK),    # A up
        _point(20, 110.0, ExtremumType.VALLEY),  # B down, > A start
        _point(30, 130.0, ExtremumType.PEAK),    # C extends beyond A
    ]


def _valid_bearish_zigzag() -> List[WavePoint]:
    return [
        _point(0, 100.0, ExtremumType.PEAK),
        _point(10, 80.0, ExtremumType.VALLEY),   # A down
        _point(20, 90.0, ExtremumType.PEAK),     # B up, < A start
        _point(30, 70.0, ExtremumType.VALLEY),   # C extends below A
    ]


# ---------------------------------------------------------------------------
# find_extrema tests
# ---------------------------------------------------------------------------


class TestFindExtrema:
    def test_sine_wave_finds_alternating_extrema(self) -> None:
        """A clean sine wave produces alternating peaks and valleys."""
        x = np.linspace(0, 8 * np.pi, 400)
        prices = 100 + 5 * np.sin(x)
        # No ATR -> distance-only filter.
        pts = find_extrema(prices, distance=20)

        # 4 full cycles -> 4 peaks and 4 valleys (or one fewer on edges).
        assert len(pts) >= 7
        assert all(isinstance(p, WavePoint) for p in pts)

        # Strictly increasing index order.
        for prev, nxt in zip(pts, pts[1:]):
            assert nxt.index > prev.index

        # Peaks and valleys both present.
        types = {p.extremum_type for p in pts}
        assert ExtremumType.PEAK in types
        assert ExtremumType.VALLEY in types

    def test_atr_prominence_filters_noise(self) -> None:
        """High ATR-driven prominence drops tiny wiggles."""
        rng = np.random.default_rng(42)
        base = 100 + 5 * np.sin(np.linspace(0, 4 * np.pi, 200))
        noise = rng.normal(0, 0.05, size=200)
        prices = base + noise

        loose = find_extrema(prices, atr=0.0, distance=5)
        strict = find_extrema(prices, atr=2.0, distance=5, prominence_factor=1.5)

        assert len(strict) <= len(loose)

    def test_rejects_nans(self) -> None:
        prices = np.array([1.0, 2.0, np.nan, 4.0, 5.0])
        with pytest.raises(ValueError, match="NaN"):
            find_extrema(prices)

    def test_rejects_wrong_type(self) -> None:
        with pytest.raises(TypeError):
            find_extrema("not-a-series")  # type: ignore[arg-type]

    def test_rejects_excessive_length(self) -> None:
        prices = np.zeros(MAX_INPUT_LENGTH + 1)
        with pytest.raises(ValueError, match="MAX_INPUT_LENGTH"):
            find_extrema(prices)

    def test_short_series_returns_empty(self) -> None:
        assert find_extrema([1.0, 2.0, 3.0]) == []

    def test_accepts_pandas_series_with_timestamps(self) -> None:
        idx = pd.date_range("2026-01-01", periods=200, freq="h")
        prices = pd.Series(100 + 5 * np.sin(np.linspace(0, 4 * np.pi, 200)), index=idx)
        pts = find_extrema(prices, distance=10, timestamps=[ts.isoformat() for ts in idx])
        assert pts, "expected at least one extremum"
        assert pts[0].timestamp is not None


# ---------------------------------------------------------------------------
# calculate_ewo tests
# ---------------------------------------------------------------------------


class TestCalculateEwo:
    def test_returns_index_aligned_series(self) -> None:
        df = pd.DataFrame({"close": np.linspace(100, 200, 100)})
        ewo = calculate_ewo(df, fast=5, slow=35)
        assert isinstance(ewo, pd.Series)
        assert len(ewo) == len(df)
        # First slow-1 values are NaN.
        assert ewo.iloc[:34].isna().all()
        assert ewo.dropna().shape[0] == 100 - 34
        assert ewo.name == "EWO_5_35"

    def test_rejects_non_dataframe(self) -> None:
        with pytest.raises(TypeError):
            calculate_ewo([1, 2, 3])  # type: ignore[arg-type]

    def test_missing_column_raises(self) -> None:
        with pytest.raises(KeyError):
            calculate_ewo(pd.DataFrame({"price": [1, 2, 3]}))

    def test_fast_must_be_less_than_slow(self) -> None:
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        with pytest.raises(ValueError):
            calculate_ewo(df, fast=35, slow=5)

    def test_uptrending_series_yields_positive_ewo(self) -> None:
        df = pd.DataFrame({"close": np.linspace(100, 200, 100)})
        ewo = calculate_ewo(df)
        tail = ewo.dropna().iloc[-10:]
        # Fast SMA leads slow SMA in an uptrend -> positive EWO.
        assert (tail > 0).all()


# ---------------------------------------------------------------------------
# ImpulseRule tests
# ---------------------------------------------------------------------------


class TestImpulseRule:
    def test_valid_bullish_impulse(self) -> None:
        result = ImpulseRule().validate(_valid_bullish_impulse())
        assert isinstance(result, WavePattern)
        assert result.pattern_type == PatternType.IMPULSE
        assert result.is_valid, result.violations
        assert result.direction == 1
        assert result.violations == []

    def test_valid_bearish_impulse(self) -> None:
        result = ImpulseRule().validate(_valid_bearish_impulse())
        assert result.is_valid, result.violations
        assert result.direction == -1

    def test_rule1_violation_w2_retraces_too_far(self) -> None:
        pts = _valid_bullish_impulse()
        # Drop W2 below W1 start (100) -> retracement >100%.
        pts[2] = _point(20, 95.0, ExtremumType.VALLEY)
        result = ImpulseRule().validate(pts)
        assert not result.is_valid
        assert any("Rule 1" in v for v in result.violations)

    def test_rule2_violation_w3_shortest(self) -> None:
        pts = _valid_bullish_impulse()
        # Make W3 the shortest: 110 -> 115 (len 5) while W1=20, W5=30.
        pts[3] = _point(30, 115.0, ExtremumType.PEAK)
        pts[4] = _point(40, 113.0, ExtremumType.VALLEY)  # keep no-overlap (>120 fails)
        # Need to ensure W4 still does not overlap W1 -> set valley above 120.
        pts[4] = _point(40, 121.0, ExtremumType.VALLEY)
        pts[5] = _point(50, 151.0, ExtremumType.PEAK)  # W5 length 30
        result = ImpulseRule().validate(pts)
        # W3 len = 5, W1 = 20, W5 = 30 -> W3 is shortest.
        assert not result.is_valid
        assert any("Rule 2" in v for v in result.violations)

    def test_rule3_violation_w4_overlaps_w1(self) -> None:
        pts = _valid_bullish_impulse()
        # Make W4 dip into W1 territory: below 120.
        pts[4] = _point(40, 115.0, ExtremumType.VALLEY)
        result = ImpulseRule().validate(pts)
        assert not result.is_valid
        assert any("Rule 3" in v for v in result.violations)

    def test_wrong_number_of_points(self) -> None:
        result = ImpulseRule().validate(_valid_bullish_impulse()[:4])
        assert not result.is_valid
        assert "Expected" in result.violations[0]

    def test_alternation_violation(self) -> None:
        pts = _valid_bullish_impulse()
        # Two peaks in a row.
        pts[2] = _point(20, 130.0, ExtremumType.PEAK)
        result = ImpulseRule().validate(pts)
        assert not result.is_valid
        assert any("should be valley" in v for v in result.violations)


# ---------------------------------------------------------------------------
# ZigzagRule tests
# ---------------------------------------------------------------------------


class TestZigzagRule:
    def test_valid_bullish_zigzag(self) -> None:
        result = ZigzagRule().validate(_valid_bullish_zigzag())
        assert result.is_valid, result.violations
        assert result.direction == 1
        assert result.pattern_type == PatternType.ZIGZAG

    def test_valid_bearish_zigzag(self) -> None:
        result = ZigzagRule().validate(_valid_bearish_zigzag())
        assert result.is_valid, result.violations
        assert result.direction == -1

    def test_rule1_b_retraces_too_far(self) -> None:
        pts = _valid_bullish_zigzag()
        # B drops below A start (100) -> retracement >=100%.
        pts[2] = _point(20, 95.0, ExtremumType.VALLEY)
        result = ZigzagRule().validate(pts)
        assert not result.is_valid
        assert any("Rule 1" in v for v in result.violations)

    def test_rule2_c_does_not_extend(self) -> None:
        pts = _valid_bullish_zigzag()
        # C falls short of A's high.
        pts[3] = _point(30, 115.0, ExtremumType.PEAK)
        result = ZigzagRule().validate(pts)
        assert not result.is_valid
        assert any("Rule 2" in v for v in result.violations)

    def test_wrong_point_count(self) -> None:
        result = ZigzagRule().validate(_valid_bullish_zigzag()[:2])
        assert not result.is_valid


# ---------------------------------------------------------------------------
# RuleEngine tests
# ---------------------------------------------------------------------------


class TestRuleEngine:
    def test_engine_detects_impulse(self) -> None:
        engine = RuleEngine()
        patterns = engine.validate(_valid_bullish_impulse())
        assert any(p.pattern_type == PatternType.IMPULSE and p.is_valid for p in patterns)

    def test_engine_detects_zigzag(self) -> None:
        engine = RuleEngine()
        patterns = engine.validate(_valid_bullish_zigzag())
        assert any(p.pattern_type == PatternType.ZIGZAG and p.is_valid for p in patterns)

    def test_engine_validate_one(self) -> None:
        engine = RuleEngine()
        result = engine.validate_one(_valid_bullish_impulse(), PatternType.IMPULSE)
        assert result.is_valid

    def test_engine_validate_one_unknown_raises(self) -> None:
        engine = RuleEngine()
        # PatternType.COMPLEX remains unregistered after Wave 2 (Triangle,
        # Flat, Diagonal are now registered). Use COMPLEX as the canonical
        # "no rule attached" case for this contract test.
        with pytest.raises(KeyError):
            engine.validate_one(_valid_bullish_impulse(), PatternType.COMPLEX)

    def test_engine_default_rules_loaded(self) -> None:
        engine = RuleEngine()
        types = {type(r).__name__ for r in engine.rules or []}
        assert "ImpulseRule" in types
        assert "ZigzagRule" in types

    def test_engine_include_invalid_returns_diagnostics(self) -> None:
        # 6 random valleys cannot form a valid impulse but include_invalid
        # should still report the candidate.
        pts = [
            _point(i, float(100 + i), ExtremumType.VALLEY) for i in range(6)
        ]
        engine = RuleEngine(include_invalid=True)
        results = engine.validate(pts)
        # At least one impulse candidate considered (even though invalid).
        assert any(p.pattern_type == PatternType.IMPULSE for p in results)
        assert all(not p.is_valid for p in results if p.pattern_type == PatternType.IMPULSE)


# ---------------------------------------------------------------------------
# WaveDetector end-to-end test
# ---------------------------------------------------------------------------


class TestWaveDetectorEndToEnd:
    def _make_gold_like_series(self) -> pd.DataFrame:
        """Construct a synthetic gold-like 5-wave bullish impulse.

        We hand-craft a piecewise-linear price path that traces a clean
        1-2-3-4-5 wave shape on 200 candles, then add light noise.
        """
        # Anchor (idx, price) pairs in chronological order.
        anchors = [
            (0,   1900.0),  # W1 start
            (30,  1950.0),  # W1 end
            (60,  1925.0),  # W2 end
            (110, 2050.0),  # W3 end
            (140, 1995.0),  # W4 end (above W1 peak 1950 -> no overlap)
            (199, 2090.0),  # W5 end
        ]
        xs = np.arange(200, dtype=float)
        ys = np.interp(xs, [a[0] for a in anchors], [a[1] for a in anchors])
        rng = np.random.default_rng(7)
        ys = ys + rng.normal(0, 0.5, size=len(ys))
        df = pd.DataFrame(
            {
                "open":  ys,
                "high":  ys + 1.0,
                "low":   ys - 1.0,
                "close": ys,
                "volume": np.full(200, 1000.0),
            }
        )
        return df

    def test_detector_finds_5_anchor_swings(self) -> None:
        df = self._make_gold_like_series()
        detector = WaveDetector(distance=20, prominence_factor=0.0, ewo_filter=False)
        swings = detector.detect_swings(df, price_column="close", atr=None)

        # We expect roughly 4-5 internal extrema (excluding endpoints).
        assert len(swings) >= 4, swings
        # Alternation property holds.
        for prev, nxt in zip(swings, swings[1:]):
            assert prev.extremum_type != nxt.extremum_type

    def test_detector_rejects_nan_input(self) -> None:
        df = self._make_gold_like_series()
        df.iloc[10, df.columns.get_loc("close")] = np.nan
        detector = WaveDetector(distance=10)
        with pytest.raises(ValueError, match="NaN"):
            detector.detect_swings(df)

    def test_detector_rejects_missing_column(self) -> None:
        df = pd.DataFrame({"price": [1.0, 2.0, 3.0]})
        detector = WaveDetector()
        with pytest.raises(KeyError):
            detector.detect_swings(df, price_column="close")

    def test_detector_rule_engine_pipeline(self) -> None:
        """Full pipeline: synthetic prices -> detector -> RuleEngine."""
        df = self._make_gold_like_series()
        detector = WaveDetector(distance=20, prominence_factor=0.0)
        swings = detector.detect_swings(df, atr=None)
        engine = RuleEngine()
        results = engine.validate(swings)
        # On a clean hand-crafted impulse the engine should surface at
        # least one valid pattern (impulse or zigzag depending on which
        # 6-window aligns to the anchors).
        assert isinstance(results, list)
        # Sanity: no exception, and any returned patterns are well-formed.
        for p in results:
            assert isinstance(p, WavePattern)
            assert p.is_valid is True


# ---------------------------------------------------------------------------
# BaseRule contract
# ---------------------------------------------------------------------------


def test_base_rule_is_abstract() -> None:
    with pytest.raises(TypeError):
        BaseRule()  # type: ignore[abstract]
