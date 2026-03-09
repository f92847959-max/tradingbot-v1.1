"""Multi-timeframe data consistency tests.

Verifies correct handling of missing timeframes, stale data,
empty DataFrames, and timestamp synchronization issues.
"""

import numpy as np
import pandas as pd
import pytest

from ai_engine.features.feature_engineer import FeatureEngineer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candle_df(n: int = 100, freq: str = "5min", seed: int = 42) -> pd.DataFrame:
    """Create a synthetic candle DataFrame."""
    np.random.seed(seed)
    base = 2045 + np.cumsum(np.random.randn(n) * 0.3)
    timestamps = pd.date_range("2026-02-01 08:00", periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": base + np.random.randn(n) * 0.2,
        "high": base + np.abs(np.random.randn(n)) * 0.4,
        "low": base - np.abs(np.random.randn(n)) * 0.4,
        "close": base,
        "volume": np.random.randint(500, 2000, n),
        "rsi_14": np.random.uniform(30, 70, n),
        "ema_9": base + np.random.randn(n) * 0.1,
        "ema_21": base + np.random.randn(n) * 0.05,
    }, index=timestamps)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMTFDataGap:
    def test_mtf_data_with_empty_timeframe(self):
        """One timeframe has empty DataFrame → no crash, features still created."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")
        mtf_data = {
            "5m": primary,
            "15m": pd.DataFrame(),  # Empty
            "1h": _make_candle_df(30, "1h"),
        }

        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert len(result) > 0
        # trend_15m should be 0 (no data)
        assert "trend_15m" in result.columns
        assert result["trend_15m"].iloc[-1] == 0

    def test_mtf_missing_indicators(self):
        """Timeframe data without EMA columns → trend defaults to 0."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")
        # No ema_9/ema_21 in 15m data
        bare_df = pd.DataFrame({
            "open": [2045, 2046],
            "high": [2047, 2048],
            "low": [2043, 2044],
            "close": [2046, 2047],
            "volume": [1000, 1200],
        })
        mtf_data = {
            "5m": primary,
            "15m": bare_df,
        }

        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert result["trend_15m"].iloc[-1] == 0


class TestMTFEmptyDataFrame:
    def test_empty_primary_returns_empty(self):
        """Empty primary DataFrame → returns empty (no crash)."""
        fe = FeatureEngineer()
        empty = pd.DataFrame({"open": [], "high": [], "low": [], "close": [], "volume": []})
        result = fe.create_features(empty, timeframe="5m")
        assert len(result) == 0

    def test_all_mtf_empty(self):
        """All multi-TF data empty → features still computed from primary."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")
        mtf_data = {
            "15m": pd.DataFrame(),
            "1h": pd.DataFrame(),
        }
        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert len(result) == 100


class TestMTFAlignment:
    def test_tf_alignment_all_bullish(self):
        """All timeframes bullish → tf_alignment = 1."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")

        # Create MTF data where ema_9 > ema_21 (bullish) on all
        def _bullish_df(n, freq):
            np.random.seed(42)
            base = 2045 + np.cumsum(np.random.randn(n) * 0.1)
            ts = pd.date_range("2026-02-01 08:00", periods=n, freq=freq, tz="UTC")
            return pd.DataFrame({
                "open": base, "high": base + 1, "low": base - 1, "close": base,
                "volume": np.ones(n) * 1000,
                "ema_9": base + 2,   # Above ema_21
                "ema_21": base + 1,
            }, index=ts)

        mtf_data = {
            "5m": _bullish_df(100, "5min"),
            "15m": _bullish_df(30, "15min"),
            "1h": _bullish_df(10, "1h"),
        }

        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert "tf_alignment" in result.columns
        # All bullish → alignment should be 1
        assert result["tf_alignment"].iloc[-1] == 1

    def test_tf_alignment_mixed_direction(self):
        """Different trend directions → tf_alignment = 0."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")

        base = np.array([2045.0])
        bullish = pd.DataFrame({
            "open": base, "high": base + 1, "low": base - 1, "close": base,
            "volume": [1000], "ema_9": base + 2, "ema_21": base + 1,
        })
        bearish = pd.DataFrame({
            "open": base, "high": base + 1, "low": base - 1, "close": base,
            "volume": [1000], "ema_9": base - 2, "ema_21": base - 1,  # ema_9 < ema_21
        })

        mtf_data = {
            "5m": bullish,
            "15m": bearish,
        }

        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert result["tf_alignment"].iloc[-1] == 0


class TestMTFRSIValues:
    def test_rsi_from_other_timeframe(self):
        """RSI values from other timeframes are extracted correctly."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")

        tf15_df = pd.DataFrame({
            "open": [2045], "high": [2046], "low": [2044], "close": [2045],
            "volume": [1000], "rsi_14": [72.5],
            "ema_9": [2046], "ema_21": [2044],
        })

        mtf_data = {"15m": tf15_df}
        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert "rsi_15m" in result.columns
        assert result["rsi_15m"].iloc[-1] == pytest.approx(72.5)

    def test_rsi_defaults_to_50_when_missing(self):
        """Missing rsi_14 in timeframe data → defaults to 50."""
        fe = FeatureEngineer()
        primary = _make_candle_df(100, "5min")

        no_rsi = pd.DataFrame({
            "open": [2045], "high": [2046], "low": [2044], "close": [2045],
            "volume": [1000], "ema_9": [2046], "ema_21": [2044],
        })

        mtf_data = {"1h": no_rsi}
        result = fe.create_features(primary.copy(), timeframe="5m", multi_tf_data=mtf_data)
        assert result["rsi_1h"].iloc[-1] == pytest.approx(50.0)
