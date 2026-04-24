"""Tests for the optional specialist runtime overlay."""

from __future__ import annotations

import copy

import pandas as pd

from ai_engine.prediction.ensemble import EnsemblePredictor
from ai_engine.prediction.specialist import SpecialistRuntime


def _frame(close_values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "close": close_values,
            "atr_14": [1.2 for _ in close_values],
        }
    )


def _analysis(
    timeframe: str,
    *,
    action: str,
    model_action: str | None = None,
    confidence: float = 0.72,
    specialist_prediction: dict | None = None,
) -> dict:
    result = {
        "timeframe": timeframe,
        "samples": 2,
        "latest_price": 2050.0,
        "model_votes": {
            "xgboost": {
                "action": action,
                "confidence": confidence,
                "probabilities": [0.10, 0.10, 0.80],
                "weight": 0.55,
            }
        },
        "model_action": model_action or action,
        "model_confidence": confidence,
        "indicator_score": 0.25 if action == "BUY" else -0.25 if action == "SELL" else 0.0,
        "indicator_components": {},
        "indicator_snapshot": {},
        "combined_score": 0.34 if action == "BUY" else -0.34 if action == "SELL" else 0.0,
        "action": action,
        "confidence": confidence,
        "agreement_count": 1,
        "regime": "trending",
        "ensemble_probabilities": {"SELL": 0.10, "HOLD": 0.10, "BUY": 0.80},
        "reasoning": [f"{timeframe}:{action}"],
        "feature_names": ["f1"],
        "_latest_features": pd.Series({"f1": 1.0}),
    }
    if specialist_prediction is not None:
        result["specialist_prediction"] = specialist_prediction
    return result


def _signal_without_timestamp(signal: dict) -> dict:
    normalized = copy.deepcopy(signal)
    normalized.pop("timestamp", None)
    return normalized


def test_specialist_adapter_returns_noop_when_artifacts_missing() -> None:
    runtime = SpecialistRuntime(saved_models_dir="missing-specialist-root")
    prediction = runtime.predict_from_feature_frame(pd.DataFrame({"close": [1.0]}))

    assert prediction.available is False
    assert prediction.action == "HOLD"
    assert "missing" in prediction.reason


def test_ensemble_preserves_baseline_when_specialist_disabled() -> None:
    candle_data = {"5m": _frame([2049.0, 2050.0])}

    disabled = EnsemblePredictor(
        specialist_enabled=False,
        min_confidence=0.1,
        decision_threshold=0.1,
    )
    missing = EnsemblePredictor(
        specialist_enabled=True,
        min_confidence=0.1,
        decision_threshold=0.1,
    )
    disabled._models_loaded = True
    missing._models_loaded = True

    analysis = _analysis("5m", action="BUY")
    disabled._analyze_single_timeframe = lambda timeframe, tf_df, candle_data: analysis
    missing._analyze_single_timeframe = lambda timeframe, tf_df, candle_data: analysis

    disabled_signal = disabled.predict(candle_data, primary_timeframe="5m")
    missing_signal = missing.predict(candle_data, primary_timeframe="5m")

    assert _signal_without_timestamp(disabled_signal) == _signal_without_timestamp(missing_signal)


def test_ensemble_logs_specialist_fields_and_confirm_effect() -> None:
    predictor = EnsemblePredictor(
        specialist_enabled=True,
        min_confidence=0.1,
        decision_threshold=0.1,
    )
    predictor._models_loaded = True
    predictor._analyze_single_timeframe = lambda timeframe, tf_df, candle_data: _analysis(
        timeframe,
        action="BUY",
        specialist_prediction={
            "name": "market_structure_liquidity",
            "available": True,
            "action": "BUY",
            "confidence": 0.88,
            "score": 0.41,
            "reason": "market_structure_liquidity_confirm_buy",
        },
    )

    signal = predictor.predict({"5m": _frame([2050.0, 2051.0])}, primary_timeframe="5m")

    final_aggregation = signal["final_aggregation"]
    assert final_aggregation["core_action"] == "BUY"
    assert final_aggregation["specialist_score"] == 0.41
    assert final_aggregation["specialist_confidence"] == 0.88
    assert final_aggregation["specialist_reason"] == "market_structure_liquidity_confirm_buy"
    assert final_aggregation["specialist_effect"] == "confirm"


def test_ensemble_specialist_cannot_trade_alone_when_core_is_hold() -> None:
    predictor = EnsemblePredictor(
        specialist_enabled=True,
        min_confidence=0.1,
        decision_threshold=0.1,
    )
    predictor._models_loaded = True
    predictor._analyze_single_timeframe = lambda timeframe, tf_df, candle_data: _analysis(
        timeframe,
        action="HOLD",
        model_action="HOLD",
        confidence=0.20,
        specialist_prediction={
            "name": "market_structure_liquidity",
            "available": True,
            "action": "BUY",
            "confidence": 0.91,
            "score": 0.38,
            "reason": "market_structure_liquidity_confirm_buy",
        },
    )

    signal = predictor.predict({"5m": _frame([2050.0, 2050.2])}, primary_timeframe="5m")

    assert signal["action"] == "HOLD"
    assert "specialist_only_rejected" in signal["final_aggregation"]["gate_reasons"]
    assert signal["final_aggregation"]["specialist_effect"] == "specialist_only_rejected"
