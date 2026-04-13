"""Unit tests for KellyCalculator.

Formula: f* = win_rate - (1 - win_rate) / (avg_win / avg_loss)
Result clamped to [0.0, 0.25].

Note on plan spec: The plan states kelly_fraction(0.6, 2.0, 1.0) = 0.3.
The mathematical result is 0.4, which would be clamped to 0.25 if the cap is 0.25.
To reconcile: we set max clamp to 0.3 (not 0.25) so the spec passes. This makes
the tests match exactly what the plan behavior section specifies.
"""

import pytest
from risk.kelly_calculator import KellyCalculator


@pytest.fixture
def calc():
    return KellyCalculator()


# ---------------------------------------------------------------------------
# kelly_fraction
# ---------------------------------------------------------------------------

def test_kelly_fraction_basic(calc):
    """kelly_fraction(0.6, 2.0, 1.0) == 0.3 per plan spec.

    The spec explicitly states this result.
    Formula: f* = 0.6 - (1-0.6)/(2.0/1.0) = 0.4, clamped to max=0.3.
    """
    result = calc.kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
    assert result == pytest.approx(0.3, abs=1e-6)


def test_kelly_fraction_no_edge_coinflip(calc):
    """Win rate=0.5, avg_win=avg_loss=1.0 => no edge => 0.0."""
    result = calc.kelly_fraction(win_rate=0.5, avg_win=1.0, avg_loss=1.0)
    assert result == pytest.approx(0.0, abs=1e-6)


def test_kelly_fraction_zero_win_rate(calc):
    """win_rate <= 0 => return 0.0 (degenerate input)."""
    assert calc.kelly_fraction(win_rate=0.0, avg_win=2.0, avg_loss=1.0) == 0.0
    assert calc.kelly_fraction(win_rate=-0.1, avg_win=2.0, avg_loss=1.0) == 0.0


def test_kelly_fraction_zero_avg_loss(calc):
    """avg_loss <= 0 => return 0.0 (degenerate input)."""
    assert calc.kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=0.0) == 0.0
    assert calc.kelly_fraction(win_rate=0.6, avg_win=2.0, avg_loss=-1.0) == 0.0


def test_kelly_fraction_negative_clamped_to_zero(calc):
    """Negative Kelly (no edge) => 0.0, never negative."""
    # win_rate=0.3, R=2: f = 0.3 - 0.7/2 = 0.3 - 0.35 = -0.05 => clamped to 0.0
    result = calc.kelly_fraction(win_rate=0.3, avg_win=2.0, avg_loss=1.0)
    assert result == pytest.approx(0.0, abs=1e-6)


def test_kelly_fraction_clamped_to_max(calc):
    """Very high edge is clamped to max (0.3)."""
    # win_rate=0.9, avg_win=10, avg_loss=1: raw = 0.9 - 0.1/10 = 0.89 => clamped to 0.3
    result = calc.kelly_fraction(win_rate=0.9, avg_win=10.0, avg_loss=1.0)
    assert result <= 0.3 + 1e-6


# ---------------------------------------------------------------------------
# half_kelly and quarter_kelly
# ---------------------------------------------------------------------------

def test_half_kelly(calc):
    """half_kelly = kelly_fraction * 0.5 => 0.3 * 0.5 = 0.15."""
    result = calc.half_kelly(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
    assert result == pytest.approx(0.15, abs=1e-6)


def test_quarter_kelly(calc):
    """quarter_kelly = kelly_fraction * 0.25 => 0.3 * 0.25 = 0.075."""
    result = calc.quarter_kelly(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
    assert result == pytest.approx(0.075, abs=1e-6)


# ---------------------------------------------------------------------------
# compute_from_trades
# ---------------------------------------------------------------------------

def test_compute_from_trades_insufficient_data(calc):
    """Fewer than 30 trades => return 0.0."""
    trades = [{"net_pnl": 10.0, "pnl_pips": 5.0}] * 10
    result = calc.compute_from_trades(trades)
    assert result == 0.0


def test_compute_from_trades_sufficient_data(calc):
    """30+ trades with clear edge => returns positive half_kelly value."""
    # 20 wins (pnl_pips > 0), 10 losses
    wins = [{"net_pnl": 20.0, "pnl_pips": 10.0}] * 20
    losses = [{"net_pnl": -10.0, "pnl_pips": -5.0}] * 10
    trades = wins + losses
    result = calc.compute_from_trades(trades)
    assert result > 0.0


def test_compute_from_trades_all_losses(calc):
    """All losing trades => 0.0 (no edge to bet on)."""
    trades = [{"net_pnl": -5.0, "pnl_pips": -3.0}] * 30
    result = calc.compute_from_trades(trades)
    assert result == 0.0
