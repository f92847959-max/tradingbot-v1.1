"""Unit tests for VolatilitySizer -- RED phase (written before implementation)."""

import pytest
from risk.volatility_sizer import VolatilitySizer


@pytest.fixture
def sizer():
    """Default sizer: baseline_atr=3.0, min_scale=0.25, max_scale=1.5."""
    return VolatilitySizer()


# ---------------------------------------------------------------------------
# calculate_atr_factor
# ---------------------------------------------------------------------------

def test_atr_factor_neutral(sizer):
    """ATR equals baseline => factor == 1.0."""
    result = sizer.calculate_atr_factor(atr=3.0)
    assert result == pytest.approx(1.0, abs=1e-6)


def test_atr_factor_double_volatility(sizer):
    """ATR double the baseline => factor == 0.5."""
    result = sizer.calculate_atr_factor(atr=6.0)
    assert result == pytest.approx(0.5, abs=1e-6)


def test_atr_factor_half_volatility_clamped(sizer):
    """ATR half the baseline => unclamped factor = 2.0 but max_scale=1.5."""
    result = sizer.calculate_atr_factor(atr=1.5)
    assert result == pytest.approx(1.5, abs=1e-6)  # clamped to max_scale


def test_atr_factor_zero_atr_no_division_error(sizer):
    """ATR = 0 must not cause ZeroDivisionError; result is clamped within [min_scale, max_scale]."""
    result = sizer.calculate_atr_factor(atr=0.0)
    # atr=0 => safe_atr=0.01 => raw_factor = 3.0/0.01 = 300 => clamped to max_scale=1.5
    assert result == pytest.approx(sizer.max_scale, abs=1e-6)
    assert sizer.min_scale <= result <= sizer.max_scale


def test_atr_factor_respects_custom_params():
    """Custom baseline/min/max are respected."""
    s = VolatilitySizer(baseline_atr=5.0, min_scale=0.1, max_scale=2.0)
    # atr=10 => factor = 5/10 = 0.5, within [0.1, 2.0] => 0.5
    assert s.calculate_atr_factor(atr=10.0) == pytest.approx(0.5, abs=1e-6)
    # atr=1.0 => factor = 5/1 = 5.0, clamped to 2.0
    assert s.calculate_atr_factor(atr=1.0) == pytest.approx(2.0, abs=1e-6)


# ---------------------------------------------------------------------------
# adjust_lot_size
# ---------------------------------------------------------------------------

def test_adjust_lot_size_double_atr(sizer):
    """base_lot=1.0, atr=6.0 (double baseline) => adjusted = 0.5."""
    result = sizer.adjust_lot_size(base_lot=1.0, atr=6.0)
    assert result == pytest.approx(0.5, abs=0.01)


def test_adjust_lot_size_min_lot_floor(sizer):
    """Very high ATR should not return a lot below min_lot_size."""
    # Extreme ATR: 100 => factor = 3/100 = 0.03 < min_scale 0.25 => factor=0.25
    # base_lot=0.01 => adjusted=0.01*0.25=0.0025 => clamped to min_lot_size=0.01
    result = sizer.adjust_lot_size(base_lot=0.01, atr=100.0, min_lot_size=0.01)
    assert result >= 0.01


def test_adjust_lot_size_rounded(sizer):
    """Result is rounded to 2 decimal places."""
    result = sizer.adjust_lot_size(base_lot=1.0, atr=3.0)  # factor=1.0, lot=1.0
    assert result == round(result, 2)
