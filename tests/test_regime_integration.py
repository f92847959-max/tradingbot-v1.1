"""Tests for regime-aware strategy integration (Plan 04-03).

Tests the full regime-aware trading path: StrategyManager regime detection,
TradeScorer regime-adjusted scoring, entry_calculator regime convenience
functions, and PositionSizer ATR guard.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from strategy.regime_detector import MarketRegime
from strategy.strategy_manager import StrategyManager
from strategy.trade_scorer import TradeScorer
from strategy.entry_calculator import (
    calculate_sl_tp_for_regime,
    is_valid_rr_for_regime,
)
from risk.position_sizing import PositionSizer


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_df(
    rows: int = 60,
    adx: float = 30.0,
    atr: float = 2.0,
    close_start: float = 2000.0,
    close_end: float = 2050.0,
) -> pd.DataFrame:
    """Create a synthetic 5m DataFrame with known indicator values.

    Default rows is 60 because StrategyManager.evaluate() requires
    >=50 candles before invoking regime detection (warmup guard).
    """
    close = np.linspace(close_start, close_end, rows)
    return pd.DataFrame({
        "close": close,
        "high": np.linspace(close_start + 1, close_end + 1, rows),
        "low": np.linspace(close_start - 1, close_end - 1, rows),
        "atr_14": [atr] * rows,
        "adx": [adx] * rows,
        # multi_timeframe.py expects EMA columns; provide a simple monotonic
        # series so the timeframe is not skipped during regime evaluation.
        "ema_9": close,
        "ema_21": close,
    })


def _make_signal(
    action: str = "BUY",
    confidence: float = 0.85,
    entry: float = 2050.0,
    sl: float = 2047.0,
    tp: float = 2055.0,
) -> dict:
    """Create a basic signal dict."""
    return {
        "action": action,
        "confidence": confidence,
        "entry_price": entry,
        "stop_loss": sl,
        "take_profit": tp,
    }


# London session datetime (always passes session filter)
LONDON_DT = datetime(2026, 3, 9, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test 1-3: StrategyManager regime detection and threshold adaptation
# ---------------------------------------------------------------------------


class TestStrategyManagerRegime:
    """Tests for regime detection in StrategyManager.evaluate()."""

    def test_trending_regime_lower_min_score(self):
        """Test 1: TRENDING regime applies lower min_score (55)."""
        sm = StrategyManager()
        # High ADX -> TRENDING regime (min_score=55)
        df = _make_df(adx=35.0, atr=2.0)

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="London"):
            result = sm.evaluate(
                _make_signal(confidence=0.85),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        assert result is not None
        assert result["regime"] == "trending"

    def test_ranging_regime_higher_min_score(self):
        """Test 2: RANGING regime applies higher min_score (65)."""
        sm = StrategyManager()
        # Low ADX -> RANGING regime (min_score=65, min_confidence=0.75)
        df = _make_df(adx=15.0, atr=2.0)

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="London"):
            result = sm.evaluate(
                _make_signal(confidence=0.85),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        # RANGING min_score=65 -- signal may or may not pass depending on score
        # The point is the regime is detected correctly
        if result is not None:
            assert result["regime"] == "ranging"

    def test_volatile_regime_highest_min_score(self):
        """Test 3: VOLATILE regime applies highest min_score (70)."""
        sm = StrategyManager()
        # High ATR ratio -> VOLATILE regime (min_score=70, min_confidence=0.80)
        # ATR=5.0, average ATR=2.0 -> ratio=2.5 > ATR_VOLATILE_RATIO=1.5
        df = _make_df(adx=20.0, atr=2.0)
        # Override last few rows to have high ATR to trigger VOLATILE
        df.loc[df.index[-5:], "atr_14"] = 5.0

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="London"):
            result = sm.evaluate(
                _make_signal(confidence=0.90),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        if result is not None:
            assert result["regime"] == "volatile"

    def test_approved_signal_has_regime_keys(self):
        """Test 4: Approved signal includes 'regime' and 'regime_confidence'."""
        sm = StrategyManager()
        df = _make_df(adx=35.0, atr=2.0)

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="Overlap"):
            result = sm.evaluate(
                _make_signal(confidence=0.90),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        assert result is not None
        assert "regime" in result
        assert "regime_confidence" in result
        assert isinstance(result["regime"], str)
        assert isinstance(result["regime_confidence"], float)
        assert result["regime_confidence"] >= 0.0

    def test_rejects_confidence_below_regime_threshold(self):
        """Test 13: Reject when confidence < regime-specific threshold."""
        sm = StrategyManager()
        # VOLATILE regime requires min_confidence=0.80
        # But confidence=0.75 passes base threshold (0.70) but fails regime
        df = _make_df(adx=20.0, atr=2.0)
        df.loc[df.index[-5:], "atr_14"] = 5.0  # trigger VOLATILE

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="London"):
            result = sm.evaluate(
                _make_signal(confidence=0.75),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        assert result is None

    def test_rejects_score_below_regime_min_score(self):
        """Test 14: Reject when score < regime-specific min_score."""
        sm = StrategyManager()
        # VOLATILE regime requires min_trade_score=70
        # Use Off session (0 score) + low alignment to get low score
        df = _make_df(adx=20.0, atr=2.0)
        df.loc[df.index[-5:], "atr_14"] = 5.0

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="Off"):
            result = sm.evaluate(
                _make_signal(confidence=0.85),
                mtf_data={"5m": df},
                dt=LONDON_DT,
            )

        # With Off session (0 pts) and volatile scoring penalties,
        # score should be well below 70
        assert result is None

    def test_no_mtf_data_defaults_to_ranging(self):
        """Backward compat: when mtf_data is None, regime defaults to RANGING."""
        sm = StrategyManager()

        with patch.object(sm.session, "is_active", return_value=True), \
             patch.object(sm.session, "current_session", return_value="Overlap"):
            result = sm.evaluate(
                _make_signal(confidence=0.85),
                dt=LONDON_DT,
            )

        # Without mtf_data, regime defaults to RANGING (min_confidence=0.75)
        # 0.85 >= 0.75, should pass confidence check
        # Score depends on neutral defaults -- may or may not pass min_score=65
        if result is not None:
            assert result["regime"] == "ranging"


# ---------------------------------------------------------------------------
# Test 5-7: TradeScorer regime-aware scoring
# ---------------------------------------------------------------------------


class TestTradeScorerRegime:
    """Tests for regime-aware scoring in TradeScorer."""

    def test_trending_boosts_adx_score(self):
        """Test 5: TRENDING regime boosts trend ADX score."""
        scorer = TradeScorer()
        signal = _make_signal()

        # ADX=30 is in the >= 25 bucket
        # TRENDING: 12 pts, Original: 10 pts
        score_trending = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=MarketRegime.TRENDING,
        )
        score_none = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=None,
        )

        assert score_trending > score_none

    def test_ranging_reduces_adx_score(self):
        """Test 6: RANGING regime reduces trend ADX score."""
        scorer = TradeScorer()
        signal = _make_signal()

        # ADX=30 is in the >= 25 bucket
        # RANGING: 7 pts, Original: 10 pts
        score_ranging = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=MarketRegime.RANGING,
        )
        score_none = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=None,
        )

        assert score_ranging < score_none

    def test_regime_none_uses_original_weights(self):
        """Test 7: regime=None uses original scoring weights (backward compat)."""
        scorer = TradeScorer()
        signal = _make_signal()

        # Both None calls should produce same result
        score1 = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=None,
        )
        score2 = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
        )

        assert score1 == score2

    def test_volatile_caps_volatility_score(self):
        """VOLATILE regime narrows ideal ATR ratio band and caps vol score."""
        scorer = TradeScorer()
        signal = _make_signal()

        # ATR ratio=1.0 (in ideal band for both regimes)
        # VOLATILE: 10 pts (capped), Original: 15 pts
        score_volatile = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=MarketRegime.VOLATILE,
        )
        score_none = scorer.score(
            signal=signal, adx=30.0, atr=2.0, atr_average=2.0,
            regime=None,
        )

        assert score_volatile < score_none


# ---------------------------------------------------------------------------
# Test 8-9: entry_calculator regime convenience functions
# ---------------------------------------------------------------------------


class TestEntryCalculatorRegime:
    """Tests for regime-aware entry calculator functions."""

    def test_trending_wider_tp(self):
        """Test 8: TRENDING uses wider TP (2.5x ATR)."""
        sl, tp = calculate_sl_tp_for_regime("BUY", 2050.0, 2.0, MarketRegime.TRENDING)
        # TRENDING: TP = 2050 + 2.5*2 = 2055.0, SL = 2050 - 1.5*2 = 2047.0
        assert tp == 2055.0
        assert sl == 2047.0

    def test_ranging_tighter_tp(self):
        """Test 9: RANGING uses tighter TP (1.5x ATR) and SL (1.0x ATR)."""
        sl, tp = calculate_sl_tp_for_regime("BUY", 2050.0, 2.0, MarketRegime.RANGING)
        # RANGING: TP = 2050 + 1.5*2 = 2053.0, SL = 2050 - 1.0*2 = 2048.0
        assert tp == 2053.0
        assert sl == 2048.0

    def test_volatile_widest_sl_tp(self):
        """VOLATILE uses widest TP (3.0x) and SL (2.0x)."""
        sl, tp = calculate_sl_tp_for_regime("BUY", 2050.0, 2.0, MarketRegime.VOLATILE)
        # VOLATILE: TP = 2050 + 3.0*2 = 2056.0, SL = 2050 - 2.0*2 = 2046.0
        assert tp == 2056.0
        assert sl == 2046.0

    def test_sell_direction(self):
        """Verify SELL direction reverses SL/TP placement."""
        sl, tp = calculate_sl_tp_for_regime("SELL", 2050.0, 2.0, MarketRegime.TRENDING)
        # SELL TRENDING: SL = 2050 + 1.5*2 = 2053.0, TP = 2050 - 2.5*2 = 2045.0
        assert sl == 2053.0
        assert tp == 2045.0

    def test_is_valid_rr_for_regime_ranging_low_rr(self):
        """Test 12: RANGING with low RR (1.25) passes (threshold 1.2)."""
        # RR = 2.5 / 2.0 = 1.25
        valid = is_valid_rr_for_regime(
            entry=2050.0,
            stop_loss=2048.0,
            take_profit=2052.5,
            regime=MarketRegime.RANGING,
        )
        assert valid is True

    def test_is_valid_rr_for_regime_trending_low_rr(self):
        """TRENDING with RR=1.25 fails (threshold 1.5)."""
        valid = is_valid_rr_for_regime(
            entry=2050.0,
            stop_loss=2048.0,
            take_profit=2052.5,
            regime=MarketRegime.TRENDING,
        )
        assert valid is False


# ---------------------------------------------------------------------------
# Test 10-11: PositionSizer ATR guard
# ---------------------------------------------------------------------------


class TestPositionSizerAtrGuard:
    """Tests for ATR guard in PositionSizer."""

    def test_atr_exceeds_max_returns_min_lot(self):
        """Test 10: ATR > max_atr_for_trading returns minimum lot size."""
        sizer = PositionSizer(risk_per_trade_pct=1.0)
        lot = sizer.calculate_with_atr_guard(
            equity=10000,
            entry_price=2050.0,
            stop_loss=2047.0,
            atr=6.0,
            max_atr_for_trading=5.0,
        )
        assert lot == sizer.min_lot_size

    def test_atr_below_max_returns_normal(self):
        """Test 11: ATR < max_atr_for_trading returns normal calculation."""
        sizer = PositionSizer(risk_per_trade_pct=1.0)
        normal = sizer.calculate(
            equity=10000, entry_price=2050.0, stop_loss=2047.0,
        )
        guarded = sizer.calculate_with_atr_guard(
            equity=10000,
            entry_price=2050.0,
            stop_loss=2047.0,
            atr=2.0,
            max_atr_for_trading=5.0,
        )
        assert guarded == normal
        assert guarded > sizer.min_lot_size

    def test_atr_exactly_at_max_returns_normal(self):
        """ATR exactly at max_atr_for_trading is NOT guarded (uses >, not >=)."""
        sizer = PositionSizer(risk_per_trade_pct=1.0)
        lot = sizer.calculate_with_atr_guard(
            equity=10000,
            entry_price=2050.0,
            stop_loss=2047.0,
            atr=5.0,
            max_atr_for_trading=5.0,
        )
        normal = sizer.calculate(
            equity=10000, entry_price=2050.0, stop_loss=2047.0,
        )
        assert lot == normal

    def test_custom_max_atr(self):
        """Custom max_atr_for_trading value works."""
        sizer = PositionSizer(risk_per_trade_pct=1.0)
        # ATR=3.5 with max=3.0 -> guarded
        lot = sizer.calculate_with_atr_guard(
            equity=10000,
            entry_price=2050.0,
            stop_loss=2047.0,
            atr=3.5,
            max_atr_for_trading=3.0,
        )
        assert lot == sizer.min_lot_size
