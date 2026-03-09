"""Tests fuer PromptBuilder."""

from __future__ import annotations

import numpy as np
import pandas as pd

from ai_engine.features.feature_engineer import FeatureEngineer
from ai_engine.prediction.prompt_builder import PromptBuilder


def _df(n: int, freq: str) -> pd.DataFrame:
    np.random.seed(7)
    timestamps = pd.date_range("2026-02-23 09:00", periods=n, freq=freq, tz="UTC")
    base = 2045 + np.cumsum(np.random.randn(n) * 0.15)
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base + np.random.randn(n) * 0.1,
            "high": base + np.abs(np.random.randn(n)) * 0.2,
            "low": base - np.abs(np.random.randn(n)) * 0.2,
            "close": base,
            "volume": np.random.randint(600, 1600, n),
            "rsi_14": np.clip(50 + np.random.randn(n) * 7, 10, 90),
            "macd_line": np.random.randn(n) * 0.2,
            "macd_signal": np.random.randn(n) * 0.2,
            "macd_hist": np.random.randn(n) * 0.1,
            "ema_9": base + 0.2,
            "ema_21": base - 0.05,
            "ema_50": base - 0.2,
            "ema_200": 2040.0,
            "bb_width": np.random.uniform(0.005, 0.02, n),
            "adx_14": np.random.uniform(15, 35, n),
            "stoch_k": np.random.uniform(20, 80, n),
            "stoch_d": np.random.uniform(20, 80, n),
            "atr_14": np.random.uniform(0.8, 1.6, n),
            "pivot": 2045.0,
            "pivot_s1": 2040.0,
            "pivot_r1": 2050.0,
            "vwap": 2045.6,
        }
    )
    df.index = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _build_prompt(max_candles: int = 30) -> str:
    df_5m = _df(90, "5min")
    df_1m = _df(90, "1min")
    df_15m = _df(90, "15min")
    multi_tf_data = {"1m": df_1m, "5m": df_5m, "15m": df_15m}

    fe = FeatureEngineer()
    features_df = fe.create_features(df_5m, timeframe="5m", multi_tf_data=multi_tf_data)
    builder = PromptBuilder(max_candles_in_prompt=max_candles)
    return builder.build_user_prompt(
        primary_df=df_5m,
        features_df=features_df,
        multi_tf_data=multi_tf_data,
        primary_timeframe="5m",
    )


def test_prompt_contains_candle_data() -> None:
    prompt = _build_prompt()
    assert "## Recent Candles" in prompt
    assert "Time | Open | High | Low | Close | Vol" in prompt


def test_prompt_contains_indicators() -> None:
    prompt = _build_prompt()
    assert "RSI(14):" in prompt
    assert "MACD:" in prompt
    assert "EMA9:" in prompt
    assert "ATR(14):" in prompt


def test_prompt_contains_multi_tf() -> None:
    prompt = _build_prompt()
    assert "## Multi-Timeframe Context" in prompt
    assert "1m:" in prompt
    assert "15m:" in prompt
    assert "Alignment:" in prompt


def test_prompt_max_candles() -> None:
    prompt = _build_prompt(max_candles=30)
    candles_section = prompt.split("## Recent Candles", 1)[1].split("## Technical Indicators", 1)[0]
    lines = [line for line in candles_section.splitlines() if line.strip()]
    # Header + table header + max 30 Candle-Zeilen
    assert len(lines) <= 32


def test_prompt_contains_session() -> None:
    prompt = _build_prompt()
    assert "Session:" in prompt
