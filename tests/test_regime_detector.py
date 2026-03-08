"""Tests for market regime detection.

Covers RegimeDetector classification logic, hysteresis, detect_series,
regime parameter lookup, and edge cases (NaN, empty data, missing columns).
"""

import numpy as np
import pandas as pd
import pytest

from strategy.regime_detector import MarketRegime, RegimeDetector, RegimeState
from strategy.regime_params import REGIME_PARAMS, get_regime_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    adx: float = 22.0,
    atr: float = 1.5,
    n_rows: int = 25,
    adx_col: str = "adx",
) -> pd.DataFrame:
    """Build a minimal DataFrame for regime detection tests."""
    return pd.DataFrame({
        "close": [2000.0] * n_rows,
        "high": [2001.0] * n_rows,
        "low": [1999.0] * n_rows,
        "atr_14": [atr] * n_rows,
        adx_col: [adx] * n_rows,
        "bb_bandwidth": [0.02] * n_rows,
    })


# ---------------------------------------------------------------------------
# Test 1: High ADX -> TRENDING
# ---------------------------------------------------------------------------

class TestTrendingDetection:
    def test_high_adx_is_trending(self):
        """ADX 30+ with normal ATR should classify as TRENDING."""
        df = _make_df(adx=30.0, atr=1.5)
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.TRENDING

    def test_very_high_adx_high_confidence(self):
        """ADX 40 should give confidence close to 1.0."""
        df = _make_df(adx=40.0, atr=1.5)
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.TRENDING
        assert state.confidence >= 0.9


# ---------------------------------------------------------------------------
# Test 2: Low ADX -> RANGING
# ---------------------------------------------------------------------------

class TestRangingDetection:
    def test_low_adx_is_ranging(self):
        """ADX < 20 with normal ATR should classify as RANGING."""
        df = _make_df(adx=15.0, atr=1.5)
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.RANGING

    def test_very_low_adx_high_confidence(self):
        """ADX 10 should give high confidence."""
        df = _make_df(adx=10.0, atr=1.5)
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.RANGING
        assert state.confidence >= 0.9


# ---------------------------------------------------------------------------
# Test 3: High ATR ratio -> VOLATILE
# ---------------------------------------------------------------------------

class TestVolatileDetection:
    def test_high_atr_ratio_is_volatile(self):
        """ATR > 1.5x average should classify as VOLATILE regardless of ADX."""
        # Build DataFrame where last row has ATR spike
        n = 25
        atr_values = [1.0] * (n - 1) + [2.0]  # spike on last row
        df = pd.DataFrame({
            "close": [2000.0] * n,
            "high": [2001.0] * n,
            "low": [1999.0] * n,
            "atr_14": atr_values,
            "adx": [30.0] * n,  # Would be TRENDING without ATR spike
            "bb_bandwidth": [0.02] * n,
        })
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.VOLATILE

    def test_volatile_overrides_trending(self):
        """VOLATILE has highest priority, overriding TRENDING ADX."""
        n = 25
        atr_values = [1.0] * (n - 1) + [3.0]  # Big spike
        df = pd.DataFrame({
            "close": [2000.0] * n,
            "high": [2001.0] * n,
            "low": [1999.0] * n,
            "atr_14": atr_values,
            "adx": [35.0] * n,
            "bb_bandwidth": [0.02] * n,
        })
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.VOLATILE


# ---------------------------------------------------------------------------
# Test 4 & 5: Ambiguous ADX zone (20-25)
# ---------------------------------------------------------------------------

class TestAmbiguousZone:
    def test_ambiguous_low_atr_is_ranging(self):
        """ADX 22 with low ATR ratio -> RANGING."""
        df = _make_df(adx=22.0, atr=1.0)  # Normal ATR, ratio ~1.0
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.RANGING

    def test_ambiguous_high_atr_is_trending(self):
        """ADX 22 with elevated ATR ratio -> TRENDING."""
        n = 25
        # ATR values: low for most, elevated at end to push ratio > 1.2
        atr_values = [1.0] * (n - 5) + [1.3] * 5
        df = pd.DataFrame({
            "close": [2000.0] * n,
            "high": [2001.0] * n,
            "low": [1999.0] * n,
            "atr_14": atr_values,
            "adx": [22.0] * n,
            "bb_bandwidth": [0.02] * n,
        })
        detector = RegimeDetector()
        state = detector.detect(df)
        # With ATR ratio > 1.2 in ambiguous zone, should tip toward TRENDING
        assert state.regime == MarketRegime.TRENDING


# ---------------------------------------------------------------------------
# Test 6: NaN ATR handling
# ---------------------------------------------------------------------------

class TestNaNHandling:
    def test_nan_atr_returns_ranging_zero_confidence(self):
        """NaN ATR should return RANGING with confidence 0."""
        df = _make_df(adx=30.0, atr=1.0)
        df.iloc[-1, df.columns.get_loc("atr_14")] = np.nan
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.RANGING
        assert state.confidence == 0.0

    def test_empty_dataframe(self):
        """Empty DataFrame should return RANGING with confidence 0."""
        df = pd.DataFrame()
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.RANGING
        assert state.confidence == 0.0


# ---------------------------------------------------------------------------
# Test 7: detect_series returns correct length and types
# ---------------------------------------------------------------------------

class TestDetectSeries:
    def test_series_length_matches_input(self):
        """detect_series should return same-length Series."""
        df = _make_df(adx=30.0, atr=1.5, n_rows=50)
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert len(result) == len(df)
        assert isinstance(result, pd.Series)

    def test_series_contains_regime_enums(self):
        """All values should be MarketRegime enum members."""
        df = _make_df(adx=30.0, atr=1.5, n_rows=20)
        detector = RegimeDetector()
        result = detector.detect_series(df)
        for val in result:
            assert isinstance(val, MarketRegime)

    def test_series_trending_regime(self):
        """High ADX in all rows -> all TRENDING."""
        df = _make_df(adx=35.0, atr=1.5, n_rows=30)
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert (result == MarketRegime.TRENDING).all()

    def test_series_volatile_overrides(self):
        """ATR spike rows should be VOLATILE regardless of ADX."""
        n = 30
        # Use a large spike so ratio stays above 1.5 even as rolling avg adjusts
        atr_values = [1.0] * 25 + [3.0] * 5
        df = pd.DataFrame({
            "close": [2000.0] * n,
            "high": [2001.0] * n,
            "low": [1999.0] * n,
            "atr_14": atr_values,
            "adx": [30.0] * n,
            "bb_bandwidth": [0.02] * n,
        })
        detector = RegimeDetector()
        result = detector.detect_series(df)
        # First spike row (index 25) should be VOLATILE
        assert result.iloc[25] == MarketRegime.VOLATILE

    def test_series_empty_dataframe(self):
        """Empty DataFrame should return empty Series."""
        df = pd.DataFrame()
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert len(result) == 0

    def test_series_uses_adx_14_fallback(self):
        """Should use adx_14 column when adx is not present."""
        df = pd.DataFrame({
            "close": [2000.0] * 25,
            "high": [2001.0] * 25,
            "low": [1999.0] * 25,
            "atr_14": [1.5] * 25,
            "adx_14": [35.0] * 25,  # Using adx_14 instead of adx
            "bb_bandwidth": [0.02] * 25,
        })
        detector = RegimeDetector()
        result = detector.detect_series(df)
        assert (result == MarketRegime.TRENDING).all()


# ---------------------------------------------------------------------------
# Test 8: Hysteresis prevents regime flickering
# ---------------------------------------------------------------------------

class TestHysteresis:
    def test_single_candle_flicker_rejected(self):
        """Regime should NOT switch on a single-candle deviation."""
        detector = RegimeDetector(min_confirm_candles=3)

        # Establish TRENDING
        df_trending = _make_df(adx=30.0, atr=1.5)
        state = detector.detect(df_trending)
        assert state.regime == MarketRegime.TRENDING

        # One candle of RANGING data -- should NOT switch
        df_ranging = _make_df(adx=15.0, atr=1.5)
        state = detector.detect(df_ranging)
        assert state.regime == MarketRegime.TRENDING  # Still TRENDING

    def test_confirmed_switch_after_min_candles(self):
        """Regime should switch after min_confirm_candles consecutive detections."""
        detector = RegimeDetector(min_confirm_candles=3)

        # Establish TRENDING
        df_trending = _make_df(adx=30.0, atr=1.5)
        detector.detect(df_trending)

        # 3 consecutive RANGING candles -> should switch
        df_ranging = _make_df(adx=15.0, atr=1.5)
        detector.detect(df_ranging)  # count=1
        detector.detect(df_ranging)  # count=2
        state = detector.detect(df_ranging)  # count=3 -> switch
        assert state.regime == MarketRegime.RANGING

    def test_flicker_resets_counter(self):
        """If regime flickers back, the confirmation counter resets."""
        detector = RegimeDetector(min_confirm_candles=3)

        # Establish TRENDING
        df_trending = _make_df(adx=30.0, atr=1.5)
        detector.detect(df_trending)

        # 2 RANGING, then 1 TRENDING -> counter should reset
        df_ranging = _make_df(adx=15.0, atr=1.5)
        detector.detect(df_ranging)  # count=1
        detector.detect(df_ranging)  # count=2
        detector.detect(df_trending)  # back to TRENDING -> reset

        # 2 more RANGING -> should NOT switch (only 2, not 3)
        detector.detect(df_ranging)  # count=1
        state = detector.detect(df_ranging)  # count=2
        assert state.regime == MarketRegime.TRENDING  # Not yet


# ---------------------------------------------------------------------------
# Test 9: get_regime_params returns correct keys for each regime
# ---------------------------------------------------------------------------

class TestRegimeParams:
    EXPECTED_KEYS = {
        "tp_atr_multiplier",
        "sl_atr_multiplier",
        "min_confidence",
        "min_trade_score",
        "rr_min",
    }

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_params_have_all_keys(self, regime):
        """Each regime should have all expected parameter keys."""
        params = get_regime_params(regime)
        assert set(params.keys()) == self.EXPECTED_KEYS

    @pytest.mark.parametrize("regime", list(MarketRegime))
    def test_params_values_are_numeric(self, regime):
        """All parameter values should be numeric (int or float)."""
        params = get_regime_params(regime)
        for key, value in params.items():
            assert isinstance(value, (int, float)), (
                f"{regime.value}.{key} = {value} is not numeric"
            )

    def test_trending_wider_tp_than_ranging(self):
        """TRENDING should have wider TP than RANGING."""
        trending = get_regime_params(MarketRegime.TRENDING)
        ranging = get_regime_params(MarketRegime.RANGING)
        assert trending["tp_atr_multiplier"] > ranging["tp_atr_multiplier"]

    def test_volatile_widest_sl(self):
        """VOLATILE should have the widest SL multiplier."""
        volatile = get_regime_params(MarketRegime.VOLATILE)
        trending = get_regime_params(MarketRegime.TRENDING)
        ranging = get_regime_params(MarketRegime.RANGING)
        assert volatile["sl_atr_multiplier"] > trending["sl_atr_multiplier"]
        assert volatile["sl_atr_multiplier"] > ranging["sl_atr_multiplier"]

    def test_volatile_highest_confidence_bar(self):
        """VOLATILE should require highest confidence."""
        volatile = get_regime_params(MarketRegime.VOLATILE)
        trending = get_regime_params(MarketRegime.TRENDING)
        assert volatile["min_confidence"] > trending["min_confidence"]


# ---------------------------------------------------------------------------
# Test 10: MarketRegime enum has exactly 3 values
# ---------------------------------------------------------------------------

class TestMarketRegimeEnum:
    def test_exactly_three_regimes(self):
        """MarketRegime should have exactly 3 members."""
        assert len(MarketRegime) == 3

    def test_regime_values(self):
        """Check string values of enum members."""
        assert MarketRegime.TRENDING.value == "trending"
        assert MarketRegime.RANGING.value == "ranging"
        assert MarketRegime.VOLATILE.value == "volatile"


# ---------------------------------------------------------------------------
# Test 11: RegimeState dataclass
# ---------------------------------------------------------------------------

class TestRegimeState:
    def test_state_fields(self):
        """RegimeState should have all expected fields."""
        state = RegimeState(
            regime=MarketRegime.TRENDING,
            adx=30.0,
            atr=1.5,
            atr_ratio=1.0,
            confidence=0.8,
        )
        assert state.regime == MarketRegime.TRENDING
        assert state.adx == 30.0
        assert state.atr == 1.5
        assert state.atr_ratio == 1.0
        assert state.confidence == 0.8


# ---------------------------------------------------------------------------
# Test 12: ADX column fallback
# ---------------------------------------------------------------------------

class TestColumnFallback:
    def test_detect_uses_adx_14_column(self):
        """detect() should use adx_14 when adx column is absent."""
        df = _make_df(adx=30.0, atr=1.5, adx_col="adx_14")
        detector = RegimeDetector()
        state = detector.detect(df)
        assert state.regime == MarketRegime.TRENDING

    def test_detect_missing_all_adx_defaults_zero(self):
        """When both adx and adx_14 are missing, ADX defaults to 0."""
        df = pd.DataFrame({
            "close": [2000.0] * 25,
            "atr_14": [1.0] * 25,
            "bb_bandwidth": [0.02] * 25,
        })
        detector = RegimeDetector()
        state = detector.detect(df)
        # ADX=0 is below range threshold -> RANGING
        assert state.regime == MarketRegime.RANGING
