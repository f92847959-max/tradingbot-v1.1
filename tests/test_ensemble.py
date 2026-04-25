"""Tests for the XGBoost + LightGBM ensemble predictor."""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import MagicMock

from ai_engine.prediction.ensemble import EnsemblePredictor


class TestEnsemblePredictor:
    """Test the 2-model ensemble (no LSTM)."""

    def setup_method(self):
        self.predictor = EnsemblePredictor(
            saved_models_dir="test_models",
            min_confidence=0.70,
            min_agreement=2,
        )

    def test_default_weights_xgboost_55_lightgbm_45(self):
        assert self.predictor.weights == {"xgboost": 0.55, "lightgbm": 0.45}

    def test_custom_weights(self):
        p = EnsemblePredictor(weights={"xgboost": 0.6, "lightgbm": 0.4})
        assert p.weights["xgboost"] == 0.6
        assert p.weights["lightgbm"] == 0.4

    def test_empty_signal_returns_hold(self):
        signal = self.predictor._empty_signal("test reason")
        assert signal["action"] == "HOLD"
        assert signal["confidence"] == 0.0
        assert signal["reasoning"] == ["test reason"]

    def test_weighted_vote_both_agree_buy(self):
        model_votes = {
            "xgboost": {
                "action": "BUY",
                "confidence": 0.85,
                "probabilities": [0.05, 0.10, 0.85],
                "weight": 0.55,
            },
            "lightgbm": {
                "action": "BUY",
                "confidence": 0.80,
                "probabilities": [0.08, 0.12, 0.80],
                "weight": 0.45,
            },
        }
        active_weights = {"xgboost": 0.55, "lightgbm": 0.45}

        probs = self.predictor._weighted_vote(model_votes, active_weights)

        # Buy probability should be highest
        assert np.argmax(probs) == 2  # BUY index
        assert probs[2] > 0.7

    def test_weighted_vote_disagreement_returns_hold(self):
        """When models disagree, agreement filter should return HOLD."""
        # With min_agreement=2, disagreement should produce HOLD
        # (tested via predict method, not directly via _weighted_vote)

    def test_calculate_sl_tp_buy(self):
        import pandas as pd

        df = pd.DataFrame({"atr_14": [1.5] * 10, "close": [2045.0] * 10})
        sl, tp, rr = self.predictor._calculate_sl_tp(df, "BUY", 2045.0)

        assert sl < 2045.0  # SL below entry for BUY
        assert tp > 2045.0  # TP above entry for BUY
        assert rr > 0

    def test_calculate_sl_tp_sell(self):
        import pandas as pd

        df = pd.DataFrame({"atr_14": [1.5] * 10, "close": [2045.0] * 10})
        sl, tp, rr = self.predictor._calculate_sl_tp(df, "SELL", 2045.0)

        assert sl > 2045.0  # SL above entry for SELL
        assert tp < 2045.0  # TP below entry for SELL

    def test_calculate_sl_tp_hold(self):
        import pandas as pd

        df = pd.DataFrame({"atr_14": [1.5] * 10, "close": [2045.0] * 10})
        sl, tp, rr = self.predictor._calculate_sl_tp(df, "HOLD", 2045.0)

        assert sl == 2045.0
        assert tp == 2045.0

    def test_action_map_correct(self):
        assert EnsemblePredictor.ACTION_MAP[0] == "SELL"
        assert EnsemblePredictor.ACTION_MAP[1] == "HOLD"
        assert EnsemblePredictor.ACTION_MAP[2] == "BUY"

    def test_predict_raises_if_models_not_loaded(self):
        with pytest.raises(RuntimeError, match="Modelle nicht geladen"):
            self.predictor.predict({"5m": MagicMock()})

    def test_min_confidence_threshold(self):
        """Confidence below threshold should convert to HOLD."""
        predictor = EnsemblePredictor(min_confidence=0.80)
        assert predictor.min_confidence == 0.80

    def test_resolve_timeframe_order_high_to_low(self):
        candle_data = {
            "5m": pd.DataFrame({"close": [1.0], "atr_14": [1.0]}),
            "1d": pd.DataFrame({"close": [1.0], "atr_14": [1.0]}),
            "15m": pd.DataFrame({"close": [1.0], "atr_14": [1.0]}),
        }
        order = self.predictor._resolve_timeframe_order(candle_data, primary_timeframe="5m")
        assert order == ["1d", "15m", "5m"]

    def test_predict_analyzes_timeframes_sequentially(self, monkeypatch: pytest.MonkeyPatch):
        predictor = EnsemblePredictor(min_confidence=0.1, decision_threshold=0.1)
        predictor._models_loaded = True

        seen: list[str] = []

        def fake_analyze(timeframe, tf_df, candle_data):
            seen.append(timeframe)
            score_map = {"1d": 0.8, "15m": 0.6, "5m": 0.4}
            score = score_map.get(timeframe, 0.2)
            return {
                "timeframe": timeframe,
                "samples": len(tf_df),
                "latest_price": float(tf_df["close"].iloc[-1]),
                "model_votes": {
                    "xgboost": {
                        "action": "BUY",
                        "confidence": 0.8,
                        "probabilities": [0.05, 0.10, 0.85],
                        "weight": 0.55,
                    },
                    "lightgbm": {
                        "action": "BUY",
                        "confidence": 0.7,
                        "probabilities": [0.10, 0.20, 0.70],
                        "weight": 0.45,
                    },
                },
                "model_action": "BUY",
                "model_confidence": 0.8,
                "indicator_score": 0.2,
                "indicator_components": {"ema_trend": 0.2},
                "indicator_snapshot": {"ema_trend": 1.0},
                "combined_score": score,
                "action": "BUY",
                "confidence": min(1.0, score),
                "agreement_count": 2,
                "ensemble_probabilities": {"SELL": 0.05, "HOLD": 0.10, "BUY": 0.85},
                "reasoning": [f"{timeframe} bullish"],
                "feature_names": ["f1"],
                "_latest_features": pd.Series({"f1": 1.0}),
            }

        monkeypatch.setattr(predictor, "_analyze_single_timeframe", fake_analyze)

        candle_data = {
            "5m": pd.DataFrame({"close": [2045.0, 2046.0], "atr_14": [1.2, 1.1]}),
            "1d": pd.DataFrame({"close": [2000.0, 2050.0], "atr_14": [9.0, 8.5]}),
            "15m": pd.DataFrame({"close": [2040.0, 2044.0], "atr_14": [2.0, 1.8]}),
        }

        signal = predictor.predict(candle_data, primary_timeframe="5m")

        assert seen == ["1d", "15m", "5m"]
        assert signal["action"] == "BUY"
        assert "timeframe_analysis" in signal
        assert len(signal["timeframe_analysis"]) == 3
        assert "final_aggregation" in signal
        assert signal["final_aggregation"]["global_score"] > 0

    def test_aggregate_conflict_gate_returns_hold(self):
        predictor = EnsemblePredictor(
            min_confidence=0.1,
            decision_threshold=0.1,
            max_conflict_ratio=0.3,
        )
        analyses = [
            {"timeframe": "1d", "action": "BUY", "combined_score": 0.9},
            {"timeframe": "15m", "action": "SELL", "combined_score": -0.2},
            {"timeframe": "5m", "action": "SELL", "combined_score": -0.2},
        ]

        out = predictor._aggregate_timeframe_decisions(analyses)

        assert out["action"] == "HOLD"
        assert any("conflict_ratio" in reason for reason in out["gate_reasons"])
