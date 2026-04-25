"""Tests fuer GPTPredictor mit gemocktem OpenAI API."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

# Skip entire module if gpt_predictor module is not available
gpt_module = pytest.importorskip(
    "ai_engine.prediction.gpt_predictor",
    reason="ai_engine.prediction.gpt_predictor module not present in this build",
)
GPTPredictor = gpt_module.GPTPredictor


def _build_dataframe(
    n: int = 120,
    atr_base: float = 1.0,
    atr_last: float | None = None,
) -> pd.DataFrame:
    np.random.seed(42)
    timestamps = pd.date_range("2026-02-23 10:00", periods=n, freq="5min", tz="UTC")
    base = 2045 + np.cumsum(np.random.randn(n) * 0.2)

    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": base + np.random.randn(n) * 0.1,
            "high": base + np.abs(np.random.randn(n)) * 0.2,
            "low": base - np.abs(np.random.randn(n)) * 0.2,
            "close": base,
            "volume": np.random.randint(500, 1800, n),
            "rsi_14": np.clip(50 + np.random.randn(n) * 8, 10, 90),
            "macd_line": np.random.randn(n) * 0.2,
            "macd_signal": np.random.randn(n) * 0.2,
            "macd_hist": np.random.randn(n) * 0.1,
            "ema_9": base + 0.15,
            "ema_21": base - 0.05,
            "ema_50": base - 0.25,
            "ema_200": 2040.0,
            "bb_width": np.random.uniform(0.005, 0.02, n),
            "adx_14": np.random.uniform(18, 35, n),
            "stoch_k": np.random.uniform(20, 80, n),
            "stoch_d": np.random.uniform(20, 80, n),
            "atr_14": atr_base,
            "pivot": 2045.0,
            "pivot_s1": 2040.0,
            "pivot_r1": 2050.0,
            "vwap": 2045.5,
        }
    )

    if atr_last is not None:
        df.loc[df.index[-1], "atr_14"] = atr_last

    df.index = pd.to_datetime(df["timestamp"], utc=True)
    return df


def _build_candle_data(
    atr_base: float = 1.0,
    atr_last: float | None = None,
) -> dict[str, pd.DataFrame]:
    df_5m = _build_dataframe(n=120, atr_base=atr_base, atr_last=atr_last)
    df_1m = _build_dataframe(n=120, atr_base=atr_base, atr_last=atr_last)
    df_15m = _build_dataframe(n=120, atr_base=atr_base, atr_last=atr_last)
    return {"1m": df_1m, "5m": df_5m, "15m": df_15m}


def _fake_response(payload: dict, total_tokens: int = 200) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload), parsed=None))
        ],
        usage=SimpleNamespace(total_tokens=total_tokens),
    )


def _payload(action: str, confidence: float) -> dict:
    return {
        "action": action,
        "confidence": confidence,
        "probabilities": {
            "BUY": 0.8 if action == "BUY" else 0.1,
            "SELL": 0.8 if action == "SELL" else 0.1,
            "HOLD": 0.1,
        },
        "reasoning": [f"{action} reasoning"],
        "top_indicators": [
            {"name": "ema_trend", "value": 1.0, "importance": 0.35},
            {"name": "rsi_zone", "value": 0.0, "importance": 0.2},
        ],
    }


@pytest.mark.asyncio
async def test_predict_buy_signal() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("BUY", 0.85)))

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    assert signal["action"] == "BUY"
    assert signal["confidence"] == pytest.approx(0.85, rel=1e-3)
    assert "model_votes" in signal
    assert "gpt5" in signal["model_votes"]


@pytest.mark.asyncio
async def test_predict_sell_signal() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("SELL", 0.82)))

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    assert signal["action"] == "SELL"
    assert signal["stop_loss"] > signal["entry_price"]
    assert signal["take_profit"] < signal["entry_price"]


@pytest.mark.asyncio
async def test_predict_hold_signal() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("HOLD", 0.55)))

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    assert signal["action"] == "HOLD"
    assert signal["confidence"] == pytest.approx(0.55, rel=1e-3)


@pytest.mark.asyncio
async def test_low_confidence_becomes_hold() -> None:
    predictor = GPTPredictor(api_key="sk-test", min_confidence=0.70)
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("BUY", 0.6)))

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    assert signal["action"] == "HOLD"
    assert signal["confidence"] == pytest.approx(0.6, rel=1e-3)


@pytest.mark.asyncio
async def test_high_volatility_reduces_confidence() -> None:
    predictor = GPTPredictor(api_key="sk-test", min_confidence=0.70)
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("BUY", 0.9)))

    signal = await predictor.predict(
        _build_candle_data(atr_base=1.0, atr_last=2.0),
        primary_timeframe="5m",
    )

    assert signal["confidence"] == pytest.approx(0.9 * 0.85, rel=1e-3)


@pytest.mark.asyncio
async def test_api_timeout_returns_hold() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    predictor._call_openai = AsyncMock(return_value=None)

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    assert signal["action"] == "HOLD"
    assert signal["confidence"] == 0.0


@pytest.mark.asyncio
async def test_api_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyTimeout(Exception):
        pass

    class DummyRateLimit(Exception):
        pass

    monkeypatch.setattr(gpt_module, "APITimeoutError", DummyTimeout)
    monkeypatch.setattr(gpt_module, "RateLimitError", DummyRateLimit)
    monkeypatch.setattr(gpt_module, "AsyncOpenAI", lambda **_: MagicMock())
    monkeypatch.setattr(gpt_module.asyncio, "sleep", AsyncMock())

    predictor = GPTPredictor(api_key="sk-test", max_retries=2)
    create = AsyncMock(
        side_effect=[
            DummyRateLimit("rate-limit"),
            DummyRateLimit("rate-limit"),
            _fake_response(_payload("BUY", 0.8)),
        ]
    )
    predictor._client = MagicMock()
    predictor._client.chat = MagicMock()
    predictor._client.chat.completions = MagicMock()
    predictor._client.chat.completions.create = create

    response = await predictor._call_openai("test-prompt")

    assert response is not None
    assert create.await_count == 3


@pytest.mark.asyncio
async def test_signal_format_complete() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    predictor._call_openai = AsyncMock(return_value=_fake_response(_payload("BUY", 0.8)))

    signal = await predictor.predict(_build_candle_data(), primary_timeframe="5m")

    required_keys = {
        "action",
        "confidence",
        "timestamp",
        "entry_price",
        "stop_loss",
        "take_profit",
        "risk_reward_ratio",
        "model_votes",
        "reasoning",
        "top_features",
        "timeframe",
        "ensemble_probabilities",
    }
    assert required_keys.issubset(signal.keys())


def test_sl_tp_calculation_buy() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    df = _build_dataframe()
    entry = float(df["close"].iloc[-1])

    stop_loss, take_profit, rr = predictor._calculate_sl_tp(df, "BUY", entry)

    assert stop_loss < entry
    assert take_profit > entry
    assert rr == pytest.approx(2.0, rel=1e-3)


def test_sl_tp_calculation_sell() -> None:
    predictor = GPTPredictor(api_key="sk-test")
    df = _build_dataframe()
    entry = float(df["close"].iloc[-1])

    stop_loss, take_profit, rr = predictor._calculate_sl_tp(df, "SELL", entry)

    assert stop_loss > entry
    assert take_profit < entry
    assert rr == pytest.approx(2.0, rel=1e-3)
