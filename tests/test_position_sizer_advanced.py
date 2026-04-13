"""Unit tests for AdvancedPositionSizer and module-level get_position_size.

These tests cover:
- Basic sizing behavior
- Confidence tier mapping (low/medium/high)
- ATR scaling (higher ATR => smaller position)
- Edge cases (zero balance, clamp to min/max lot)
- set_trade_stats updates Kelly fraction
- Return dict structure
- Module-level get_position_size() function
- Settings extension fields
"""

import pytest
from risk.position_sizer import AdvancedPositionSizer, init_position_sizer, get_position_size as module_get_size


@pytest.fixture
def sizer():
    """Default AdvancedPositionSizer: base_risk_pct=1.0, half kelly, baseline_atr=3.0."""
    s = AdvancedPositionSizer(base_risk_pct=1.0, kelly_mode="half", baseline_atr=3.0)
    # Give it trade stats so Kelly data is non-zero
    s.set_trade_stats(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
    return s


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------

def test_get_position_size_returns_dict(sizer):
    """get_position_size must return a dict with required keys."""
    result = sizer.get_position_size(confidence=0.75, atr=3.0, account_balance=10000.0)
    assert isinstance(result, dict)
    for key in ("lot_size", "kelly_fraction", "atr_factor", "confidence_tier", "risk_pct", "reasoning"):
        assert key in result, f"Missing key: {key}"


def test_get_position_size_positive(sizer):
    """get_position_size(confidence=0.85, atr=3.0, account_balance=10000.0) returns lot_size > 0."""
    result = sizer.get_position_size(confidence=0.85, atr=3.0, account_balance=10000.0)
    assert result["lot_size"] > 0.0


def test_get_position_size_zero_balance(sizer):
    """Zero or negative account balance => lot_size == 0.0."""
    result_zero = sizer.get_position_size(confidence=0.85, atr=3.0, account_balance=0.0)
    assert result_zero["lot_size"] == 0.0

    result_neg = sizer.get_position_size(confidence=0.85, atr=3.0, account_balance=-100.0)
    assert result_neg["lot_size"] == 0.0


# ---------------------------------------------------------------------------
# Confidence tiers
# ---------------------------------------------------------------------------

def test_confidence_tier_low(sizer):
    """Confidence < 0.6 => tier 'low'."""
    result = sizer.get_position_size(confidence=0.5, atr=3.0, account_balance=10000.0)
    assert result["confidence_tier"] == "low"


def test_confidence_tier_medium(sizer):
    """0.6 <= confidence <= 0.8 => tier 'medium'."""
    result = sizer.get_position_size(confidence=0.7, atr=3.0, account_balance=10000.0)
    assert result["confidence_tier"] == "medium"


def test_confidence_tier_high(sizer):
    """confidence > 0.8 => tier 'high'."""
    result = sizer.get_position_size(confidence=0.9, atr=3.0, account_balance=10000.0)
    assert result["confidence_tier"] == "high"


# ---------------------------------------------------------------------------
# Scaling behavior
# ---------------------------------------------------------------------------

def test_higher_confidence_larger_lot(sizer):
    """Higher confidence => larger lot size (all else equal)."""
    low_conf = sizer.get_position_size(confidence=0.5, atr=3.0, account_balance=10000.0)
    high_conf = sizer.get_position_size(confidence=0.9, atr=3.0, account_balance=10000.0)
    assert high_conf["lot_size"] >= low_conf["lot_size"]


def test_higher_atr_smaller_lot(sizer):
    """Higher ATR => smaller lot size (all else equal)."""
    low_atr = sizer.get_position_size(confidence=0.75, atr=2.0, account_balance=10000.0)
    high_atr = sizer.get_position_size(confidence=0.75, atr=6.0, account_balance=10000.0)
    assert high_atr["lot_size"] <= low_atr["lot_size"]


# ---------------------------------------------------------------------------
# Clamp behavior
# ---------------------------------------------------------------------------

def test_lot_size_clamped_to_min(sizer):
    """Very small balance => lot clamped to min_lot_size."""
    result = sizer.get_position_size(confidence=0.5, atr=100.0, account_balance=1.0)
    assert result["lot_size"] >= sizer.min_lot_size


def test_lot_size_clamped_to_max(sizer):
    """Very large balance => lot clamped to max_lot_size."""
    result = sizer.get_position_size(confidence=0.9, atr=0.1, account_balance=10_000_000.0)
    assert result["lot_size"] <= sizer.max_lot_size


# ---------------------------------------------------------------------------
# set_trade_stats
# ---------------------------------------------------------------------------

def test_set_trade_stats_updates_kelly_fraction(sizer):
    """set_trade_stats updates internal Kelly fraction used in sizing."""
    sizer.set_trade_stats(win_rate=0.0, avg_win=1.0, avg_loss=1.0)  # no edge
    result = sizer.get_position_size(confidence=0.9, atr=3.0, account_balance=10000.0)
    # With no Kelly data, falls back to base_risk_pct (not zero)
    assert result["lot_size"] > 0.0


# ---------------------------------------------------------------------------
# Module-level get_position_size
# ---------------------------------------------------------------------------

def test_module_get_position_size_raises_before_init():
    """Module-level get_position_size raises RuntimeError if not initialized."""
    import risk.position_sizer as ps_module
    ps_module._instance = None  # ensure uninitialized

    with pytest.raises(RuntimeError, match="not initialized"):
        module_get_size(confidence=0.75, atr=3.0, account_balance=10000.0)


def test_module_init_and_get_position_size():
    """init_position_sizer creates instance; module-level func returns float."""
    from types import SimpleNamespace
    settings = SimpleNamespace(
        max_risk_per_trade_pct=1.0,
        kelly_mode="half",
        atr_baseline=3.0,
    )
    instance = init_position_sizer(settings)
    assert isinstance(instance, AdvancedPositionSizer)

    lot = module_get_size(confidence=0.75, atr=3.0, account_balance=10000.0)
    assert isinstance(lot, float)
    assert lot >= 0.0


# ---------------------------------------------------------------------------
# Settings extension
# ---------------------------------------------------------------------------

def test_settings_has_kelly_mode():
    """Settings.kelly_mode defaults to 'half'."""
    from config.settings import Settings
    s = Settings()
    assert s.kelly_mode == "half"


def test_settings_has_atr_baseline():
    """Settings.atr_baseline defaults to 3.0."""
    from config.settings import Settings
    s = Settings()
    assert s.atr_baseline == pytest.approx(3.0)


def test_settings_has_max_portfolio_heat_pct():
    """Settings.max_portfolio_heat_pct defaults to 5.0."""
    from config.settings import Settings
    s = Settings()
    assert s.max_portfolio_heat_pct == pytest.approx(5.0)


def test_settings_has_equity_curve_ema_period():
    """Settings.equity_curve_ema_period defaults to 20."""
    from config.settings import Settings
    s = Settings()
    assert s.equity_curve_ema_period == 20


def test_settings_has_equity_curve_filter_enabled():
    """Settings.equity_curve_filter_enabled defaults to True."""
    from config.settings import Settings
    s = Settings()
    assert s.equity_curve_filter_enabled is True


def test_settings_has_monte_carlo_paths():
    """Settings.monte_carlo_paths defaults to 1000."""
    from config.settings import Settings
    s = Settings()
    assert s.monte_carlo_paths == 1000
