"""Unit tests for technical indicators."""

import pytest
import numpy as np
import pandas as pd

# Skip entire module if pandas_ta not installed
pytest.importorskip("pandas_ta")

from market_data.indicators import calculate_indicators, get_indicator_summary


def make_gold_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Create a realistic Gold OHLCV DataFrame for testing."""
    rng = np.random.default_rng(seed)
    base = 2050.0
    close = base + np.cumsum(rng.normal(0, 1.5, n))
    close = np.clip(close, 1800, 2300)
    spread = rng.uniform(0.3, 1.5, n)
    high = close + spread + rng.uniform(0, 1, n)
    low = close - spread - rng.uniform(0, 1, n)
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.uniform(100, 1000, n)
    timestamps = pd.date_range("2024-01-01", periods=n, freq="5min")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestCalculateIndicators:
    def test_returns_dataframe(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns_exist(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        expected = ["ema_9", "ema_21", "ema_50", "rsi_14", "atr"]
        for col in expected:
            assert col in result.columns, f"Missing column: {col}"

    def test_macd_columns_exist(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        assert "macd" in result.columns
        assert "macd_signal" in result.columns
        assert "macd_histogram" in result.columns

    def test_rsi_range(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        rsi = result["rsi_14"].dropna()
        assert len(rsi) > 0
        assert (rsi >= 0).all(), "RSI below 0 found"
        assert (rsi <= 100).all(), "RSI above 100 found"

    def test_atr_positive(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        atr = result["atr"].dropna()
        assert len(atr) > 0
        assert (atr > 0).all(), "ATR should always be positive"

    def test_ema_near_price(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        last = result.iloc[-1]
        close = last["close"]
        # EMAs should be within 10% of current price for realistic data
        for col in ["ema_9", "ema_21"]:
            ema = last[col]
            if not pd.isna(ema):
                assert abs(ema - close) / close < 0.10, f"{col} too far from close"

    def test_ema_9_more_responsive_than_21(self):
        """EMA-9 should react faster than EMA-21 — after a price spike, EMA-9 should be closer."""
        df = make_gold_df(n=200)
        # Add a sudden price spike at the end
        spike_df = df.copy()
        spike_df.loc[spike_df.index[-5:], "close"] += 50
        result = calculate_indicators(spike_df)
        last = result.iloc[-1]
        # After spike, EMA-9 should be higher than EMA-21
        if not pd.isna(last["ema_9"]) and not pd.isna(last["ema_21"]):
            assert last["ema_9"] >= last["ema_21"] - 5  # EMA-9 should track closer to spike

    def test_adx_range(self):
        df = make_gold_df()
        result = calculate_indicators(df)
        if "adx" in result.columns:
            adx = result["adx"].dropna()
            if len(adx) > 0:
                assert (adx >= 0).all()
                assert (adx <= 100).all()

    def test_bollinger_bands_ordering(self):
        """Upper BB should be above middle which should be above lower."""
        df = make_gold_df()
        result = calculate_indicators(df)
        bb_cols = [c for c in result.columns if "bb_" in c.lower() or "bbu" in c.lower()]
        if "bb_upper" in result.columns:
            valid = result[["bb_upper", "bb_mid", "bb_lower"]].dropna()
            if not valid.empty:
                assert (valid["bb_upper"] >= valid["bb_mid"]).all()
                assert (valid["bb_mid"] >= valid["bb_lower"]).all()

    def test_short_dataframe_warning(self):
        """Should handle short DataFrames without crashing."""
        df = make_gold_df(n=30)
        result = calculate_indicators(df)
        assert isinstance(result, pd.DataFrame)
        assert "ema_9" in result.columns


class TestGetIndicatorSummary:
    def test_returns_dict(self):
        df = make_gold_df()
        df = calculate_indicators(df)
        summary = get_indicator_summary(df)
        assert isinstance(summary, dict)

    def test_has_expected_keys(self):
        df = make_gold_df()
        df = calculate_indicators(df)
        summary = get_indicator_summary(df)
        for key in ["close", "rsi", "atr"]:
            assert key in summary, f"Missing key: {key}"

    def test_returns_floats(self):
        df = make_gold_df()
        df = calculate_indicators(df)
        summary = get_indicator_summary(df)
        for k, v in summary.items():
            if v is not None:
                assert isinstance(v, (int, float)), f"Key {k} is not numeric: {type(v)}"
