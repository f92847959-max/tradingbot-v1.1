"""Shared pytest fixtures for the Gold Trader test suite."""

import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def sample_candles_df() -> pd.DataFrame:
    """Generate a realistic Gold candle DataFrame for testing (500 candles)."""
    np.random.seed(42)
    n = 500
    base_price = 2045.0
    timestamps = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")

    prices = [base_price]
    for _ in range(n - 1):
        change = np.random.randn() * 0.5
        prices.append(prices[-1] + change)

    close = np.array(prices)
    high = close + np.abs(np.random.randn(n)) * 0.3
    low = close - np.abs(np.random.randn(n)) * 0.3
    open_ = close + np.random.randn(n) * 0.2
    volume = np.random.uniform(500, 3000, n)

    return pd.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


@pytest.fixture
def sample_candles_with_indicators(sample_candles_df) -> pd.DataFrame:
    """Candle DataFrame with technical indicators pre-calculated."""
    from market_data.indicators import calculate_indicators
    return calculate_indicators(sample_candles_df.copy())


@pytest.fixture
def sample_signal_buy() -> dict:
    """A sample BUY signal from the AI engine."""
    return {
        "action": "BUY",
        "confidence": 0.82,
        "entry_price": 2045.50,
        "stop_loss": 2042.00,
        "take_profit": 2052.50,
        "trade_score": 78,
        "risk_reward_ratio": 2.0,
        "model_votes": {
            "xgboost": {"action": "BUY", "confidence": 0.85},
            "lightgbm": {"action": "BUY", "confidence": 0.79},
            "lstm": {"action": "HOLD", "confidence": 0.55},
        },
        "reasoning": ["EMA 9/21 Crossover BULLISH", "RSI bei 42 → neutral"],
        "top_features": [
            {"name": "ema_trend", "value": 1, "importance": 0.12},
            {"name": "rsi_14", "value": 42.5, "importance": 0.09},
        ],
        "timeframe": "5m",
    }


@pytest.fixture
def sample_signal_sell() -> dict:
    """A sample SELL signal from the AI engine."""
    return {
        "action": "SELL",
        "confidence": 0.75,
        "entry_price": 2050.00,
        "stop_loss": 2053.50,
        "take_profit": 2043.00,
        "trade_score": 65,
        "risk_reward_ratio": 2.0,
        "model_votes": {
            "xgboost": {"action": "SELL", "confidence": 0.78},
            "lightgbm": {"action": "SELL", "confidence": 0.73},
            "lstm": {"action": "SELL", "confidence": 0.68},
        },
        "reasoning": ["EMA 9/21 Crossover BEARISH"],
        "timeframe": "5m",
    }


@pytest.fixture
def mock_account_info() -> dict:
    """Mock Capital.com account data."""
    return {
        "balance": 10000.0,
        "available": 9500.0,
        "deposit": 10000.0,
        "profit_loss": 0.0,
    }
