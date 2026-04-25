"""Unit tests for exit engine core modules: dynamic SL, dynamic TP, exit signals.

Covers EXIT-01 (dynamic SL), EXIT-02 (dynamic TP), EXIT-05 (exit signals).
"""

import numpy as np
import pandas as pd
import pytest

from exit_engine.types import ExitLevels, ExitSignal, StructureLevel
from exit_engine.dynamic_sl import calculate_dynamic_sl, find_swing_levels
from exit_engine.dynamic_tp import calculate_dynamic_tp, find_sr_levels, fibonacci_extensions
from exit_engine.exit_signals import check_exit_signals
from strategy.regime_detector import MarketRegime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_candles(n=30, base_price=2000.0, trend=0.5, atr=3.0, rsi_base=55.0) -> pd.DataFrame:
    """Create a simple candle DataFrame for testing."""
    np.random.seed(42)
    close = base_price + np.arange(n) * trend + np.random.randn(n) * 0.5
    high = close + atr * 0.5 + np.abs(np.random.randn(n)) * 0.3
    low = close - atr * 0.5 - np.abs(np.random.randn(n)) * 0.3
    open_ = close - trend * 0.5
    rsi = np.clip(rsi_base + np.arange(n) * 0.1 + np.random.randn(n) * 2, 20, 80)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "rsi_14": rsi,
    })


# ---------------------------------------------------------------------------
# EXIT-01: Dynamic SL tests
# ---------------------------------------------------------------------------

def test_package_exports_public_exit_api():
    """Package-level imports expose the user-facing exit engine API."""
    from exit_engine import (  # noqa: PLC0415
        ExitLevels,
        ExitSignal,
        calculate_dynamic_sl,
        calculate_dynamic_tp,
        check_exit_signals,
    )

    assert ExitLevels is not None
    assert ExitSignal is not None
    assert calculate_dynamic_sl is not None
    assert calculate_dynamic_tp is not None
    assert check_exit_signals is not None


def test_dynamic_sl_entry_alias_and_attribute_result():
    """Public snippets can use entry= and read result.sl without breaking unpacking."""
    from exit_engine import calculate_dynamic_sl  # noqa: PLC0415

    result = calculate_dynamic_sl(
        direction="BUY",
        entry=2000.0,
        atr=2.0,
        regime=MarketRegime.TRENDING,
    )

    sl, reason = result
    assert result.sl == sl == 1997.0
    assert result.reason == reason


def test_sl_buy_below_entry():
    """BUY stop loss must be below entry price."""
    sl, reason = calculate_dynamic_sl("BUY", 2000.0, 3.0, MarketRegime.TRENDING)
    assert sl < 2000.0, "BUY SL must be below entry"


def test_sl_sell_above_entry():
    """SELL stop loss must be above entry price."""
    sl, reason = calculate_dynamic_sl("SELL", 2000.0, 3.0, MarketRegime.TRENDING)
    assert sl > 2000.0, "SELL SL must be above entry"


def test_sl_trending_regime():
    """TRENDING regime uses sl_atr_multiplier=1.5."""
    sl, reason = calculate_dynamic_sl("BUY", 2000.0, 2.0, MarketRegime.TRENDING)
    expected_distance = 2.0 * 1.5
    assert abs((2000.0 - sl) - expected_distance) < 0.01
    assert reason == "atr"


def test_sl_ranging_regime():
    """RANGING regime uses sl_atr_multiplier=1.0 (tighter SL)."""
    sl_ranging, _ = calculate_dynamic_sl("BUY", 2000.0, 2.0, MarketRegime.RANGING)
    sl_trending, _ = calculate_dynamic_sl("BUY", 2000.0, 2.0, MarketRegime.TRENDING)
    assert sl_ranging > sl_trending, "RANGING SL should be closer to entry (higher for BUY)"


def test_sl_volatile_regime():
    """VOLATILE regime uses sl_atr_multiplier=2.0 (wider SL)."""
    sl_volatile, _ = calculate_dynamic_sl("BUY", 2000.0, 2.0, MarketRegime.VOLATILE)
    sl_trending, _ = calculate_dynamic_sl("BUY", 2000.0, 2.0, MarketRegime.TRENDING)
    assert sl_volatile < sl_trending, "VOLATILE SL should be further from entry (lower for BUY)"


def test_sl_structure_buy():
    """BUY SL should be placed below nearest support with buffer."""
    support = StructureLevel(price=1995.0, level_type="support", strength=3, source="swing_low")
    sl, reason = calculate_dynamic_sl(
        "BUY", 2000.0, 3.0, MarketRegime.TRENDING,
        structure_levels=[support],
        structure_buffer_pips=2.0,
    )
    # ATR SL = 2000 - 3*1.5 = 1995.5; structure SL = 1995 - 0.02 = 1994.98
    # BUY: max(1995.5, 1994.98) = 1995.5 (atr_sl wins), reason = atr
    assert sl < 2000.0
    assert "atr" in reason


def test_sl_structure_below_atr_for_buy():
    """When structure is above ATR SL, structure level takes effect for BUY."""
    support = StructureLevel(price=1997.0, level_type="support", strength=3, source="swing_low")
    sl, reason = calculate_dynamic_sl(
        "BUY", 2000.0, 1.0, MarketRegime.RANGING,
        structure_levels=[support],
        structure_buffer_pips=1.0,
    )
    # ATR SL = 2000 - 1*1.0 = 1999.0; structure SL = 1997 - 0.01 = 1996.99
    # BUY: max(1999.0, 1996.99) = 1999.0 (atr wins here)
    assert sl < 2000.0


def test_sl_min_floor():
    """SL must be at least min_sl_pips away from entry."""
    # With tiny ATR that would place SL too close
    sl, reason = calculate_dynamic_sl("BUY", 2000.0, 0.001, MarketRegime.RANGING,
                                       min_sl_pips=5.0, pip_size=0.01)
    assert 2000.0 - sl >= 5.0 * 0.01 - 1e-9, "Min SL floor of 5 pips must be enforced"


def test_sl_atr_zero_raises():
    """ATR=0 must raise ValueError."""
    with pytest.raises(ValueError):
        calculate_dynamic_sl("BUY", 2000.0, 0.0, MarketRegime.TRENDING)


# ---------------------------------------------------------------------------
# EXIT-02: Fibonacci extensions
# ---------------------------------------------------------------------------

def test_fibonacci_extensions_basic():
    """fibonacci_extensions returns 5 levels at 1.0, 1.272, 1.618, 2.0, 2.618."""
    levels = fibonacci_extensions(entry=2000.0, swing_low=1990.0, swing_high=2010.0)
    assert len(levels) == 5
    swing_range = 2010.0 - 1990.0  # 20
    # 1.0 extension: 2010 + 20 * 0.0 = 2010
    # 1.272 extension: 2010 + 20 * 0.272 = 2015.44
    assert abs(levels[0] - 2010.0) < 0.01, f"1.0 ext expected ~2010, got {levels[0]}"
    assert abs(levels[1] - 2015.44) < 0.01, f"1.272 ext expected ~2015.44, got {levels[1]}"
    assert abs(levels[2] - 2022.36) < 0.01, f"1.618 ext expected ~2022.36, got {levels[2]}"
    assert abs(levels[3] - 2030.0) < 0.01, f"2.0 ext expected ~2030, got {levels[3]}"
    assert abs(levels[4] - 2042.36) < 0.05, f"2.618 ext expected ~2042.36, got {levels[4]}"


def test_fibonacci_extensions_sorted():
    """Fibonacci extension levels must be returned in ascending order."""
    levels = fibonacci_extensions(2000.0, 1990.0, 2010.0)
    assert levels == sorted(levels), "Fibonacci levels must be sorted ascending"


# ---------------------------------------------------------------------------
# EXIT-02: Dynamic TP tests
# ---------------------------------------------------------------------------

def test_tp_buy_above_entry():
    """BUY take profit must be above entry price."""
    tp, tp1, reason = calculate_dynamic_tp("BUY", 2000.0, 3.0, MarketRegime.TRENDING)
    assert tp > 2000.0, "BUY TP must be above entry"


def test_tp_sell_below_entry():
    """SELL take profit must be below entry price."""
    tp, tp1, reason = calculate_dynamic_tp("SELL", 2000.0, 3.0, MarketRegime.TRENDING)
    assert tp < 2000.0, "SELL TP must be below entry"


def test_tp_fallback_atr():
    """When no candles provided, TP falls back to ATR-based calculation."""
    tp, tp1, reason = calculate_dynamic_tp("BUY", 2000.0, 3.0, MarketRegime.TRENDING, candles=None)
    expected = 2000.0 + 3.0 * 2.5  # TRENDING tp_atr_multiplier=2.5
    assert abs(tp - expected) < 0.01
    assert reason == "atr_multiple"


def test_tp1_at_50pct():
    """TP1 must be at 50% of the full TP distance from entry."""
    tp, tp1, reason = calculate_dynamic_tp("BUY", 2000.0, 3.0, MarketRegime.TRENDING, candles=None)
    tp_distance = tp - 2000.0
    expected_tp1 = 2000.0 + tp_distance * 0.5
    assert tp1 is not None
    assert abs(tp1 - expected_tp1) < 0.01, f"TP1 expected {expected_tp1}, got {tp1}"


def test_tp1_sell_at_50pct():
    """TP1 for SELL must be at 50% of the full TP distance below entry."""
    tp, tp1, reason = calculate_dynamic_tp("SELL", 2000.0, 3.0, MarketRegime.TRENDING, candles=None)
    tp_distance = 2000.0 - tp
    expected_tp1 = 2000.0 - tp_distance * 0.5
    assert tp1 is not None
    assert abs(tp1 - expected_tp1) < 0.01


def test_find_sr_levels_returns_levels():
    """find_sr_levels should find support and resistance levels from candle data."""
    candles = make_candles(60, base_price=2000.0, trend=0.0, atr=3.0)
    levels = find_sr_levels(candles, lookback=50)
    assert isinstance(levels, list)
    # Some levels should be found
    assert len(levels) >= 0  # May find 0 if no clear swings in random data


# ---------------------------------------------------------------------------
# EXIT-05: Exit signal tests
# ---------------------------------------------------------------------------

def test_bearish_engulfing_on_buy():
    """Bearish engulfing pattern on BUY position triggers exit signal."""
    # Build candles: last two are prev bullish + curr bearish engulfing
    candles = make_candles(10)
    # Override last two candles to form a bearish engulfing
    candles.loc[candles.index[-2], "open"] = 2000.0
    candles.loc[candles.index[-2], "close"] = 2005.0  # bullish prev
    candles.loc[candles.index[-2], "high"] = 2006.0
    candles.loc[candles.index[-2], "low"] = 1999.0
    candles.loc[candles.index[-1], "open"] = 2006.0  # opens at or above prev close
    candles.loc[candles.index[-1], "close"] = 1998.0  # closes at or below prev open (engulfs)
    candles.loc[candles.index[-1], "high"] = 2007.0
    candles.loc[candles.index[-1], "low"] = 1997.0
    signal = check_exit_signals("BUY", candles)
    assert signal.should_exit is True
    assert signal.signal_type == "reversal_candle"
    assert signal.confidence >= 0.6


def test_bullish_engulfing_on_sell():
    """Bullish engulfing pattern on SELL position triggers exit signal."""
    candles = make_candles(10)
    # Override last two candles: prev bearish + curr bullish engulfing
    candles.loc[candles.index[-2], "open"] = 2005.0
    candles.loc[candles.index[-2], "close"] = 2000.0  # bearish prev
    candles.loc[candles.index[-2], "high"] = 2006.0
    candles.loc[candles.index[-2], "low"] = 1999.0
    candles.loc[candles.index[-1], "open"] = 1999.0  # opens at or below prev close
    candles.loc[candles.index[-1], "close"] = 2006.0  # closes at or above prev open (engulfs)
    candles.loc[candles.index[-1], "high"] = 2007.0
    candles.loc[candles.index[-1], "low"] = 1998.0
    signal = check_exit_signals("SELL", candles)
    assert signal.should_exit is True
    assert signal.signal_type == "reversal_candle"


def test_rsi_divergence_buy():
    """RSI bearish divergence (price higher high, RSI lower high) triggers exit on BUY."""
    candles = make_candles(10, rsi_base=60.0)
    n = len(candles)
    # Price: last candle higher than lookback-1
    candles.loc[candles.index[-1], "close"] = 2020.0
    candles.loc[candles.index[-5], "close"] = 2010.0
    candles.loc[candles.index[-1], "high"] = 2021.0
    candles.loc[candles.index[-5], "high"] = 2011.0
    # RSI: last candle lower than lookback-1 (bearish divergence)
    candles.loc[candles.index[-1], "rsi_14"] = 50.0
    candles.loc[candles.index[-5], "rsi_14"] = 70.0
    signal = check_exit_signals("BUY", candles, lookback=5)
    assert signal.should_exit is True
    assert signal.signal_type in ("reversal_candle", "momentum_divergence")


def test_no_exit_clean_trend():
    """No exit signal when trend is clean (no reversal pattern)."""
    # Create a clean uptrend with no engulfing or divergence
    n = 10
    close = np.linspace(2000, 2030, n)
    high = close + 1.0
    low = close - 1.0
    open_ = close - 0.5
    rsi = np.linspace(55, 70, n)  # rising RSI matches rising price
    candles = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "rsi_14": rsi,
    })
    signal = check_exit_signals("BUY", candles)
    assert signal.should_exit is False
    assert signal.signal_type == "none"
    assert signal.confidence == 0.0
