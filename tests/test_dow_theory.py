"""Tests for the Dow Theory trend classifier (Phase 14.1, Task 1).

Pure structural logic — every branch is covered deterministically with
synthetic ``WavePoint`` sequences and small DataFrames.
"""

from __future__ import annotations

import pandas as pd

from ai_engine.dow_theory.trend import (
    DowTrend,
    classify_primary_trend,
    confirm_with_ew,
    mtf_confirms,
    volume_confirms,
)
from ai_engine.elliott_wave.models import ExtremumType, WavePoint


def _peak(i, price):
    return WavePoint(index=i, price=price, extremum_type=ExtremumType.PEAK)


def _valley(i, price):
    return WavePoint(index=i, price=price, extremum_type=ExtremumType.VALLEY)


def _uptrend_swings():
    # HH + HL: valley 100, peak 110, valley 105, peak 120
    return [_valley(0, 100), _peak(1, 110), _valley(2, 105), _peak(3, 120)]


def _downtrend_swings():
    # LH + LL: peak 120, valley 110, peak 115, valley 100
    return [_peak(0, 120), _valley(1, 110), _peak(2, 115), _valley(3, 100)]


def _range_swings():
    # HH but LL -> not a clean Dow trend
    return [_valley(0, 100), _peak(1, 110), _valley(2, 95), _peak(3, 120)]


# --- classify_primary_trend ------------------------------------------------


def test_uptrend_detected():
    assert classify_primary_trend(_uptrend_swings()) == DowTrend.UP


def test_downtrend_detected():
    assert classify_primary_trend(_downtrend_swings()) == DowTrend.DOWN


def test_mixed_structure_is_range():
    assert classify_primary_trend(_range_swings()) == DowTrend.RANGE


def test_insufficient_pivots_is_range():
    assert classify_primary_trend([_valley(0, 100), _peak(1, 110)]) == DowTrend.RANGE


def test_empty_or_none_is_range():
    assert classify_primary_trend([]) == DowTrend.RANGE
    assert classify_primary_trend(None) == DowTrend.RANGE


# --- confirm_with_ew -------------------------------------------------------


def test_ew_confirms_uptrend():
    assert confirm_with_ew(DowTrend.UP, 1) == 1


def test_ew_contradicts_uptrend():
    assert confirm_with_ew(DowTrend.UP, -1) == -1


def test_ew_confirms_downtrend():
    assert confirm_with_ew(DowTrend.DOWN, -1) == 1


def test_ew_neutral_when_range():
    assert confirm_with_ew(DowTrend.RANGE, 1) == 0


def test_ew_neutral_when_no_ew_direction():
    assert confirm_with_ew(DowTrend.UP, 0) == 0


# --- volume_confirms -------------------------------------------------------


def test_volume_confirms_rising_participation():
    df = pd.DataFrame({"volume": [1, 1, 1, 1, 5, 6, 7]})
    assert volume_confirms(df, DowTrend.UP) is True


def test_volume_not_confirmed_when_falling():
    df = pd.DataFrame({"volume": [9, 9, 9, 9, 1, 1, 1]})
    assert volume_confirms(df, DowTrend.UP) is False


def test_volume_uses_flow_column_fallback():
    df = pd.DataFrame({"flow_imbalance": [0, 0, 0, 0, 1, 2, 3]})
    assert volume_confirms(df, DowTrend.DOWN) is True


def test_volume_unknown_without_columns():
    df = pd.DataFrame({"close": [1, 2, 3, 4, 5, 6, 7]})
    assert volume_confirms(df, DowTrend.UP) is False


def test_volume_false_on_range():
    df = pd.DataFrame({"volume": [1, 1, 1, 1, 5, 6, 7]})
    assert volume_confirms(df, DowTrend.RANGE) is False


# --- mtf_confirms ----------------------------------------------------------


def test_mtf_confirms_when_agree():
    assert mtf_confirms(DowTrend.UP, DowTrend.UP) is True


def test_mtf_not_confirmed_when_disagree():
    assert mtf_confirms(DowTrend.UP, DowTrend.DOWN) is False


def test_mtf_not_confirmed_when_higher_is_range():
    assert mtf_confirms(DowTrend.UP, DowTrend.RANGE) is False
