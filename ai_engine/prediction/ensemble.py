"""
Ensemble Predictor -- sequenzielle Multi-Timeframe-Analyse.

Analysiert alle verfuegbaren Timeframes nacheinander und bildet daraus
mit gewichteter Voting-Logik + Indikator-Score ein finales Signal.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from ..features.feature_engineer import FeatureEngineer
from ..features.feature_scaler import FeatureScaler
from ..models.xgboost_model import XGBoostModel
from ..models.lightgbm_model import LightGBMModel

logger = logging.getLogger(__name__)


class EnsemblePredictor:
    """
    Ensemble-Vorhersage durch gewichtetes Voting von Modellen und Timeframes.

    Pipeline:
    1) Timeframes nacheinander analysieren
    2) Pro Timeframe Modell+Indikator-Score berechnen
    3) Timeframe-Analysen gewichtet aggregieren
    4) Finales BUY/HOLD/SELL-Signal ableiten
    """

    ACTION_MAP = {0: "SELL", 1: "HOLD", 2: "BUY"}
    ACTION_REVERSE = {"SELL": 0, "HOLD": 1, "BUY": 2}

    DEFAULT_TIMEFRAME_WEIGHTS = {
        "1d": 0.30,
        "12h": 0.28,
        "6h": 0.27,
        "4h": 0.26,
        "2h": 0.25,
        "1h": 0.24,
        "90m": 0.23,
        "60m": 0.22,
        "45m": 0.21,
        "30m": 0.20,
        "15m": 0.18,
        "10m": 0.16,
        "5m": 0.14,
        "2m": 0.12,
        "1m": 0.10,
    }

    TIMEFRAME_ORDER = [
        "1d",
        "12h",
        "6h",
        "4h",
        "2h",
        "1h",
        "90m",
        "60m",
        "45m",
        "30m",
        "15m",
        "10m",
        "5m",
        "2m",
        "1m",
    ]

    HIGHER_TIMEFRAMES = {
        "1d",
        "12h",
        "6h",
        "4h",
        "2h",
        "1h",
        "90m",
        "60m",
        "45m",
        "30m",
        "15m",
    }

    def __init__(
        self,
        saved_models_dir: str = "ai_engine/saved_models",
        weights: dict[str, float] | None = None,
        min_confidence: float = 0.70,
        min_agreement: int = 2,
        risk_reward_ratio: float = 2.0,
        pip_size: float | None = None,
        timeframe_weights: dict[str, float] | None = None,
        model_weight: float = 0.70,
        indicator_weight: float = 0.30,
        decision_threshold: float = 0.25,
        max_conflict_ratio: float = 0.60,
        strict_high_tf_alignment: bool = True,
    ) -> None:
        if pip_size is None:
            from config.settings import get_settings

            pip_size = get_settings().instrument.pip_size

        self.saved_models_dir = saved_models_dir
        self.weights = weights or {
            "xgboost": 0.55,
            "lightgbm": 0.45,
        }
        self.min_confidence = min_confidence
        self.min_agreement = min_agreement
        self.risk_reward_ratio = risk_reward_ratio
        self.pip_size = pip_size

        self.timeframe_weights = self._build_timeframe_weights(timeframe_weights)
        self.model_weight = float(np.clip(model_weight, 0.0, 1.0))
        self.indicator_weight = float(np.clip(indicator_weight, 0.0, 1.0))
        total_weight = self.model_weight + self.indicator_weight
        if total_weight <= 0:
            self.model_weight = 0.7
            self.indicator_weight = 0.3
            total_weight = 1.0
        self.model_weight /= total_weight
        self.indicator_weight /= total_weight

        self.decision_threshold = float(max(0.01, decision_threshold))
        self.max_conflict_ratio = float(np.clip(max_conflict_ratio, 0.0, 1.0))
        self.strict_high_tf_alignment = strict_high_tf_alignment

        self._xgboost = XGBoostModel()
        self._lightgbm = LightGBMModel()
        self._scaler = FeatureScaler()
        self._feature_engineer = FeatureEngineer()

        self._models_loaded = False

    def load_models(self) -> bool:
        """Laedt alle gespeicherten Modelle. Returns True wenn mindestens eins geladen."""
        loaded_count = 0

        xgb_path = os.path.join(self.saved_models_dir, "xgboost_gold.pkl")
        if os.path.exists(xgb_path):
            try:
                self._xgboost.load(xgb_path)
                loaded_count += 1
                logger.info("XGBoost Modell geladen: %s", xgb_path)
            except (OSError, ValueError) as exc:
                logger.error("XGBoost laden fehlgeschlagen: %s", exc)

        lgb_path = os.path.join(self.saved_models_dir, "lightgbm_gold.pkl")
        if os.path.exists(lgb_path):
            try:
                self._lightgbm.load(lgb_path)
                loaded_count += 1
                logger.info("LightGBM Modell geladen: %s", lgb_path)
            except (OSError, ValueError) as exc:
                logger.error("LightGBM laden fehlgeschlagen: %s", exc)

        scaler_path = os.path.join(self.saved_models_dir, "feature_scaler.pkl")
        if os.path.exists(scaler_path):
            try:
                self._scaler.load(scaler_path)
                logger.info("Feature Scaler geladen")
            except (OSError, ValueError) as exc:
                logger.error("Scaler laden fehlgeschlagen: %s", exc)

        self._models_loaded = loaded_count > 0
        logger.info("%d/2 Modelle geladen", loaded_count)
        return self._models_loaded

    def predict(
        self,
        candle_data: dict[str, pd.DataFrame],
        primary_timeframe: str = "5m",
    ) -> dict[str, Any]:
        """Erzeugt ein finales Signal aus sequentieller Multi-Timeframe-Analyse."""
        if not self._models_loaded:
            raise RuntimeError("Modelle nicht geladen! Rufe load_models() auf.")

        if not candle_data:
            return self._empty_signal("Keine Candle-Daten verfuegbar")

        timeframe_order = self._resolve_timeframe_order(candle_data, primary_timeframe)
        analyses: list[dict[str, Any]] = []

        # Parallel timeframe analysis (CPU-bound feature engineering + prediction)
        analyzable = [
            (tf, candle_data[tf])
            for tf in timeframe_order
            if isinstance(candle_data.get(tf), pd.DataFrame) and not candle_data[tf].empty
        ]

        def _analyze(args):
            tf, tf_df = args
            return self._analyze_single_timeframe(
                timeframe=tf, tf_df=tf_df, candle_data=candle_data,
            )

        if len(analyzable) > 1:
            with ThreadPoolExecutor(max_workers=min(len(analyzable), 4)) as pool:
                futures = {pool.submit(_analyze, item): item[0] for item in analyzable}
                for future in futures:
                    tf = futures[future]
                    try:
                        analyses.append(future.result())
                    except Exception as exc:
                        logger.warning("Analyse fehlgeschlagen fuer %s: %s", tf, exc)
        else:
            for item in analyzable:
                try:
                    analyses.append(_analyze(item))
                except Exception as exc:
                    logger.warning("Analyse fehlgeschlagen fuer %s: %s", item[0], exc)

        if not analyses:
            return self._empty_signal("Keine analysierbaren Timeframes")

        aggregation = self._aggregate_timeframe_decisions(analyses)

        final_action = aggregation["action"]
        final_confidence = float(aggregation["confidence"])

        primary_tf_for_output = (
            primary_timeframe
            if primary_timeframe in candle_data and isinstance(candle_data.get(primary_timeframe), pd.DataFrame)
            else analyses[0]["timeframe"]
        )
        primary_df = candle_data.get(primary_tf_for_output)
        if not isinstance(primary_df, pd.DataFrame) or primary_df.empty:
            primary_df = candle_data.get(analyses[0]["timeframe"])

        if isinstance(primary_df, pd.DataFrame) and not primary_df.empty and "close" in primary_df.columns:
            entry_price = float(primary_df["close"].iloc[-1])
            stop_loss, take_profit, rr_ratio = self._calculate_sl_tp(primary_df, final_action, entry_price)
        else:
            entry_price = 0.0
            stop_loss, take_profit, rr_ratio = 0.0, 0.0, 0.0

        primary_analysis = next(
            (a for a in analyses if a["timeframe"] == primary_tf_for_output),
            analyses[0],
        )

        latest_features = primary_analysis.get("_latest_features")
        feature_names = primary_analysis.get("feature_names", [])
        model_votes = primary_analysis.get("model_votes", {})
        top_features = self._get_top_features(
            model_votes,
            feature_names,
            latest_features,
        )

        reasoning = self._generate_multi_tf_reasoning(
            analyses=analyses,
            aggregation=aggregation,
            final_action=final_action,
        )

        public_analysis = [self._public_timeframe_analysis(a) for a in analyses]

        signal = {
            "action": final_action,
            "confidence": final_confidence,
            "timestamp": datetime.now().isoformat(),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward_ratio": rr_ratio,
            "model_votes": model_votes,
            "reasoning": reasoning,
            "top_features": top_features,
            "timeframe": primary_tf_for_output,
            "ensemble_probabilities": aggregation["ensemble_probabilities"],
            "timeframe_analysis": public_analysis,
            "final_aggregation": {
                "global_score": aggregation["global_score"],
                "conflict_ratio": aggregation["conflict_ratio"],
                "timeframe_weights": aggregation["timeframe_weights"],
                "gate_reasons": aggregation["gate_reasons"],
                "timeframe_order": timeframe_order,
            },
        }

        logger.info(
            "Signal: %s (Konfidenz: %.1f%%, Score: %.3f, TF=%d)",
            final_action,
            final_confidence * 100,
            aggregation["global_score"],
            len(analyses),
        )

        return signal

    def _build_timeframe_weights(
        self,
        timeframe_weights: dict[str, float] | None,
    ) -> dict[str, float]:
        weights = self.DEFAULT_TIMEFRAME_WEIGHTS.copy()
        if timeframe_weights:
            for tf, value in timeframe_weights.items():
                try:
                    weight = float(value)
                except (TypeError, ValueError):
                    continue
                if weight > 0:
                    weights[tf] = weight
        return weights

    def _resolve_timeframe_order(
        self,
        candle_data: dict[str, pd.DataFrame],
        primary_timeframe: str,
    ) -> list[str]:
        available = [
            tf for tf, df in candle_data.items()
            if isinstance(df, pd.DataFrame) and not df.empty
        ]

        ordered = [tf for tf in self.TIMEFRAME_ORDER if tf in available]
        extras = sorted([tf for tf in available if tf not in ordered])
        combined = ordered + extras

        if primary_timeframe in combined:
            # Primary timeframe wird bevorzugt fuer Output genutzt,
            # Analyse-Reihenfolge bleibt bewusst von grob zu fein.
            return combined

        return combined

    def _analyze_single_timeframe(
        self,
        timeframe: str,
        tf_df: pd.DataFrame,
        candle_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        df = self._feature_engineer.create_features(
            tf_df,
            timeframe=timeframe,
            multi_tf_data=candle_data,
        )

        if df.empty:
            raise RuntimeError(f"Keine Features fuer {timeframe}")

        feature_names = self._feature_engineer.get_feature_names()

        if self._scaler.is_fitted:
            scaler_features = self._scaler.get_feature_names()
            if scaler_features:
                feature_names = scaler_features
            df = self._scaler.transform(df)

        for feature in feature_names:
            if feature not in df.columns:
                df[feature] = 0.0

        X_latest = df[feature_names].values[-1:].astype(np.float32)

        model_votes: dict[str, dict[str, Any]] = {}
        active_weights: dict[str, float] = {}

        for model_name, model, weight_key in [
            ("xgboost", self._xgboost, "xgboost"),
            ("lightgbm", self._lightgbm, "lightgbm"),
        ]:
            if not model.is_trained:
                continue
            try:
                probs = model.predict(X_latest)[0]
                action_idx = int(np.argmax(probs))
                model_votes[model_name] = {
                    "action": self.ACTION_MAP[action_idx],
                    "confidence": float(probs[action_idx]),
                    "probabilities": probs.tolist(),
                    "weight": float(self.weights.get(weight_key, 0.0)),
                }
                active_weights[model_name] = float(self.weights.get(weight_key, 0.0))
            except (ValueError, IndexError) as exc:
                logger.warning("%s Vorhersage fehlgeschlagen fuer %s: %s", model_name, timeframe, exc)

        if not model_votes:
            raise RuntimeError(f"Keine Modell-Votes fuer {timeframe}")

        ensemble_probs = self._weighted_vote(model_votes, active_weights)
        model_action = self.ACTION_MAP[int(np.argmax(ensemble_probs))]
        model_confidence = float(np.max(ensemble_probs))

        agreement_count = sum(
            1 for vote in model_votes.values() if vote.get("action") == model_action
        )
        if model_action != "HOLD" and len(model_votes) >= 2 and agreement_count < self.min_agreement:
            model_action = "HOLD"

        indicator_score, indicator_components, indicator_snapshot = self._calculate_indicator_score(df)

        model_signed_score = self._action_to_sign(model_action) * model_confidence
        combined_score = (self.model_weight * model_signed_score) + (
            self.indicator_weight * indicator_score
        )

        tf_threshold = max(0.08, self.decision_threshold * 0.5)
        action = self._score_to_action(combined_score, threshold=tf_threshold)
        confidence = float(min(1.0, abs(combined_score)))

        reasoning = self._generate_reasoning(
            features=df.iloc[-1],
            votes=model_votes,
            final_action=action,
        )

        return {
            "timeframe": timeframe,
            "samples": int(len(tf_df)),
            "latest_price": float(tf_df["close"].iloc[-1]) if "close" in tf_df.columns else 0.0,
            "model_votes": model_votes,
            "model_action": model_action,
            "model_confidence": round(model_confidence, 6),
            "indicator_score": round(float(indicator_score), 6),
            "indicator_components": indicator_components,
            "indicator_snapshot": indicator_snapshot,
            "combined_score": round(float(combined_score), 6),
            "action": action,
            "confidence": round(confidence, 6),
            "agreement_count": int(agreement_count),
            "ensemble_probabilities": {
                "SELL": float(ensemble_probs[0]),
                "HOLD": float(ensemble_probs[1]),
                "BUY": float(ensemble_probs[2]),
            },
            "reasoning": reasoning,
            "feature_names": feature_names,
            "_latest_features": df.iloc[-1],
        }

    def _calculate_indicator_score(
        self,
        feature_df: pd.DataFrame,
    ) -> tuple[float, dict[str, float], dict[str, float]]:
        latest = feature_df.iloc[-1]

        def _safe_float(name: str, default: float = 0.0) -> float:
            value = latest.get(name, default)
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        components: dict[str, float] = {}

        ema_trend = float(np.clip(_safe_float("ema_trend", 0.0), -1.0, 1.0))
        ema_50 = float(np.clip(_safe_float("ema_above_50", 0.0), -1.0, 1.0))
        ema_200 = float(np.clip(_safe_float("ema_above_200", 0.0), -1.0, 1.0))
        macd_cross = float(np.clip(_safe_float("macd_cross", 0.0), -1.0, 1.0))
        stoch_cross = float(np.clip(_safe_float("stoch_cross", 0.0), -1.0, 1.0))
        rsi_zone = float(np.clip(_safe_float("rsi_zone", 0.0), -1.0, 1.0))

        # RSI contrarian map: oversold(-1) => bullish(+0.5), overbought(+1) => bearish(-0.5)
        rsi_direction = 0.0
        if rsi_zone < 0:
            rsi_direction = 0.5
        elif rsi_zone > 0:
            rsi_direction = -0.5

        components["ema_trend"] = 0.30 * ema_trend
        components["ema_above_200"] = 0.20 * ema_200
        components["ema_above_50"] = 0.10 * ema_50
        components["macd_cross"] = 0.20 * macd_cross
        components["stoch_cross"] = 0.10 * stoch_cross
        components["rsi_zone"] = 0.10 * rsi_direction

        base_score = sum(components.values())

        adx_trending = int(_safe_float("adx_trending", 0.0))
        if adx_trending == 1 and abs(base_score) > 0.01:
            base_score *= 1.10
            components["adx_boost"] = 0.10 * np.sign(base_score)
        else:
            components["adx_boost"] = 0.0

        tf_alignment = int(_safe_float("tf_alignment", 1.0))
        if tf_alignment == 0 and abs(base_score) > 0.01:
            base_score *= 0.85
            components["tf_alignment_penalty"] = -0.05 * np.sign(base_score)
        else:
            components["tf_alignment_penalty"] = 0.0

        bb_squeeze = int(_safe_float("bb_squeeze", 0.0))
        if bb_squeeze == 1:
            base_score *= 0.95
            components["bb_squeeze_penalty"] = -0.02 * np.sign(base_score)
        else:
            components["bb_squeeze_penalty"] = 0.0

        atr_last = _safe_float("atr_14", 0.0)
        atr_mean = float(feature_df["atr_14"].mean()) if "atr_14" in feature_df.columns else 0.0
        if atr_mean > 0:
            vola_ratio = atr_last / atr_mean
            if vola_ratio > 1.5:
                base_score *= 0.85
                components["volatility_penalty"] = -0.05 * np.sign(base_score)
            else:
                components["volatility_penalty"] = 0.0
        else:
            components["volatility_penalty"] = 0.0

        indicator_score = float(np.clip(base_score, -1.0, 1.0))

        snapshot = {
            "rsi_14": _safe_float("rsi_14", 50.0),
            "ema_trend": ema_trend,
            "macd_cross": macd_cross,
            "stoch_cross": stoch_cross,
            "adx_14": _safe_float("adx_14", 0.0),
            "atr_14": atr_last,
            "bb_width": _safe_float("bb_width", 0.0),
            "tf_alignment": float(tf_alignment),
        }

        return indicator_score, {k: round(float(v), 6) for k, v in components.items()}, snapshot

    def _aggregate_timeframe_decisions(
        self,
        analyses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        weight_map = self._normalize_timeframe_weights([a["timeframe"] for a in analyses])

        global_score = 0.0
        for analysis in analyses:
            tf = analysis["timeframe"]
            tf_weight = weight_map.get(tf, 0.0)
            global_score += tf_weight * float(analysis.get("combined_score", 0.0))

        preliminary_action = self._score_to_action(global_score, self.decision_threshold)
        conflict_ratio = self._compute_conflict_ratio(analyses)

        gate_reasons: list[str] = []
        final_action = preliminary_action

        if final_action != "HOLD" and conflict_ratio > self.max_conflict_ratio:
            final_action = "HOLD"
            gate_reasons.append(
                f"conflict_ratio {conflict_ratio:.2f} > max {self.max_conflict_ratio:.2f}"
            )

        if final_action != "HOLD" and self.strict_high_tf_alignment:
            aligned, detail = self._check_higher_tf_alignment(analyses, final_action)
            if not aligned:
                final_action = "HOLD"
                gate_reasons.append(detail)

        confidence = float(min(1.0, abs(global_score)))
        if final_action != "HOLD" and confidence < self.min_confidence:
            final_action = "HOLD"
            gate_reasons.append(
                f"global_confidence {confidence:.2f} < min {self.min_confidence:.2f}"
            )

        probabilities = self._global_score_to_probabilities(
            global_score,
            hold_bias=(final_action == "HOLD"),
        )

        return {
            "action": final_action,
            "confidence": confidence,
            "global_score": round(float(global_score), 6),
            "conflict_ratio": round(float(conflict_ratio), 6),
            "timeframe_weights": {k: round(float(v), 6) for k, v in weight_map.items()},
            "gate_reasons": gate_reasons,
            "ensemble_probabilities": probabilities,
        }

    def _normalize_timeframe_weights(self, timeframes: list[str]) -> dict[str, float]:
        raw: dict[str, float] = {}
        for timeframe in timeframes:
            raw[timeframe] = float(self.timeframe_weights.get(timeframe, 0.05))

        total = sum(v for v in raw.values() if v > 0)
        if total <= 0:
            fallback = 1.0 / max(1, len(timeframes))
            return {tf: fallback for tf in timeframes}

        return {tf: weight / total for tf, weight in raw.items()}

    def _check_higher_tf_alignment(
        self,
        analyses: list[dict[str, Any]],
        action: str,
    ) -> tuple[bool, str]:
        required_sign = self._action_to_sign(action)
        higher = [
            a for a in analyses
            if a.get("timeframe") in self.HIGHER_TIMEFRAMES and a.get("action") != "HOLD"
        ]

        if not higher:
            return True, "no_higher_tf_signal"

        support = sum(1 for a in higher if self._action_to_sign(a.get("action", "HOLD")) == required_sign)
        oppose = sum(1 for a in higher if self._action_to_sign(a.get("action", "HOLD")) == -required_sign)

        if support >= oppose:
            return True, "aligned"

        return False, f"higher_tf_misaligned support={support} oppose={oppose}"

    def _compute_conflict_ratio(self, analyses: list[dict[str, Any]]) -> float:
        directions = [
            self._action_to_sign(a.get("action", "HOLD"))
            for a in analyses
            if a.get("action") != "HOLD"
        ]

        if len(directions) <= 1:
            return 0.0

        direction_sum = sum(directions)
        if direction_sum == 0:
            return 1.0

        majority = int(np.sign(direction_sum))
        conflicts = sum(1 for direction in directions if direction != majority)
        return conflicts / len(directions)

    @staticmethod
    def _action_to_sign(action: str) -> int:
        if action == "BUY":
            return 1
        if action == "SELL":
            return -1
        return 0

    @staticmethod
    def _score_to_action(score: float, threshold: float) -> str:
        if score >= threshold:
            return "BUY"
        if score <= -threshold:
            return "SELL"
        return "HOLD"

    @staticmethod
    def _global_score_to_probabilities(score: float, hold_bias: bool = False) -> dict[str, float]:
        score = float(np.clip(score, -1.0, 1.0))

        sell_raw = max(0.0, -score)
        buy_raw = max(0.0, score)
        hold_raw = max(0.0, 1.0 - abs(score))

        if hold_bias:
            hold_raw = max(hold_raw, 0.55)

        total = sell_raw + hold_raw + buy_raw
        if total <= 0:
            return {"SELL": 0.0, "HOLD": 1.0, "BUY": 0.0}

        return {
            "SELL": sell_raw / total,
            "HOLD": hold_raw / total,
            "BUY": buy_raw / total,
        }

    def _public_timeframe_analysis(self, analysis: dict[str, Any]) -> dict[str, Any]:
        return {
            "timeframe": analysis.get("timeframe"),
            "samples": analysis.get("samples"),
            "latest_price": analysis.get("latest_price"),
            "action": analysis.get("action"),
            "confidence": analysis.get("confidence"),
            "combined_score": analysis.get("combined_score"),
            "model_action": analysis.get("model_action"),
            "model_confidence": analysis.get("model_confidence"),
            "agreement_count": analysis.get("agreement_count"),
            "indicator_score": analysis.get("indicator_score"),
            "indicator_components": analysis.get("indicator_components", {}),
            "indicator_snapshot": analysis.get("indicator_snapshot", {}),
            "model_votes": analysis.get("model_votes", {}),
            "ensemble_probabilities": analysis.get("ensemble_probabilities", {}),
        }

    def _generate_multi_tf_reasoning(
        self,
        analyses: list[dict[str, Any]],
        aggregation: dict[str, Any],
        final_action: str,
    ) -> list[str]:
        reasons: list[str] = []
        reasons.append(
            f"Multi-TF Score={aggregation['global_score']:.3f}, Konflikt={aggregation['conflict_ratio']:.2f}"
        )

        tf_summaries = []
        for analysis in analyses[:5]:
            tf_summaries.append(
                f"{analysis['timeframe']}: {analysis['action']} ({analysis['confidence']:.2f})"
            )
        if tf_summaries:
            reasons.append("TF-Reihenfolge: " + " | ".join(tf_summaries))

        gate_reasons = aggregation.get("gate_reasons", [])
        if gate_reasons:
            reasons.extend([f"Gate: {reason}" for reason in gate_reasons])

        if final_action == "HOLD" and not gate_reasons:
            reasons.append("Keine klare Richtung ueber alle Timeframes")

        return reasons

    def _weighted_vote(
        self,
        model_votes: dict[str, dict],
        active_weights: dict[str, float],
    ) -> np.ndarray:
        """Berechnet gewichtetes Voting der Modelle."""
        total_weight = sum(active_weights.values())
        if total_weight <= 0:
            return np.array([0.0, 1.0, 0.0], dtype=float)

        norm_weights = {k: v / total_weight for k, v in active_weights.items()}

        ensemble_probs = np.zeros(3)
        for name, vote in model_votes.items():
            probs = np.array(vote["probabilities"])
            weight = norm_weights.get(name, 0)
            ensemble_probs += probs * weight

        return ensemble_probs

    def _calculate_sl_tp(
        self,
        df: pd.DataFrame,
        direction: str,
        entry_price: float,
    ) -> tuple[float, float, float]:
        """Berechnet Stop-Loss und Take-Profit (ATR-basiert)."""
        if "atr_14" in df.columns:
            atr = float(df["atr_14"].iloc[-1])
        else:
            atr = 1.0

        sl_distance = atr * 1.5
        tp_distance = sl_distance * self.risk_reward_ratio

        if direction == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        elif direction == "SELL":
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance
        else:
            sl = entry_price
            tp = entry_price

        rr = tp_distance / sl_distance if sl_distance > 0 else 0
        return round(sl, 2), round(tp, 2), round(rr, 2)

    def _generate_reasoning(
        self,
        features: pd.Series | None,
        votes: dict[str, dict],
        final_action: str,
    ) -> list[str]:
        """Erstellt menschenlesbare Begruendungen fuer ein einzelnes Timeframe."""
        reasons: list[str] = []

        if features is None:
            return [f"Signal: {final_action}"]

        if "rsi_zone" in features.index:
            rsi_val = features.get("rsi_14", 50)
            rsi_zone = features.get("rsi_zone", 0)
            if rsi_zone == -1:
                reasons.append(f"RSI bei {rsi_val:.0f} -> ueberverkauft")
            elif rsi_zone == 1:
                reasons.append(f"RSI bei {rsi_val:.0f} -> ueberkauft")

        if "ema_trend" in features.index:
            trend = features.get("ema_trend", 0)
            if trend == 1:
                reasons.append("EMA 9/21 Crossover BULLISH")
            elif trend == -1:
                reasons.append("EMA 9/21 Crossover BEARISH")

        if "macd_cross" in features.index:
            cross = features.get("macd_cross", 0)
            if cross == 1:
                reasons.append("MACD bullish Crossover")
            elif cross == -1:
                reasons.append("MACD bearish Crossover")

        for pattern, label in [
            ("is_engulfing_bull", "Bullish Engulfing Pattern"),
            ("is_engulfing_bear", "Bearish Engulfing Pattern"),
            ("is_hammer", "Hammer Pattern (bullish)"),
            ("is_shooting_star", "Shooting Star (bearish)"),
            ("is_doji", "Doji (Unentschlossenheit)"),
        ]:
            if pattern in features.index and features.get(pattern, 0) == 1:
                reasons.append(label)

        if features.get("is_overlap_session", 0) == 1:
            reasons.append("London+NY Overlap aktiv")
        elif features.get("is_london_session", 0) == 1:
            reasons.append("London Session aktiv")
        elif features.get("is_ny_session", 0) == 1:
            reasons.append("New York Session aktiv")

        if features.get("adx_trending", 0) == 1:
            adx = features.get("adx_14", 0)
            reasons.append(f"ADX bei {adx:.0f} (starker Trend)")

        actions = [vote["action"] for vote in votes.values()]
        unique_actions = set(actions)
        if len(unique_actions) == 1:
            reasons.append(f"Beide Modelle einig: {actions[0]}")
        else:
            vote_str = ", ".join(f"{k}={v['action']}" for k, v in votes.items())
            reasons.append(f"Modell-Votes: {vote_str}")

        if not reasons:
            reasons.append(f"Ensemble-Signal: {final_action}")

        return reasons

    def _get_top_features(
        self,
        votes: dict[str, dict],
        feature_names: list[str],
        latest_features: pd.Series | None,
        top_n: int = 5,
    ) -> list[dict[str, Any]]:
        """Gibt die wichtigsten Features zurueck."""
        all_importance: dict[str, float] = {}

        for _name, model in [("xgboost", self._xgboost), ("lightgbm", self._lightgbm)]:
            if model.is_trained:
                importance = model.get_feature_importance()
                for feature, score in importance.items():
                    all_importance[feature] = all_importance.get(feature, 0.0) + score

        total = sum(all_importance.values()) or 1.0
        normalized = {k: v / total for k, v in all_importance.items()}

        sorted_features = sorted(
            normalized.items(), key=lambda item: item[1], reverse=True
        )[:top_n]

        result: list[dict[str, Any]] = []
        for feature_name, importance in sorted_features:
            value = (
                float(latest_features.get(feature_name, 0.0))
                if latest_features is not None
                else 0.0
            )
            result.append(
                {
                    "name": feature_name,
                    "value": value,
                    "importance": round(float(importance), 4),
                }
            )

        return result

    def _empty_signal(self, reason: str) -> dict[str, Any]:
        """Gibt ein leeres HOLD-Signal zurueck."""
        return {
            "action": "HOLD",
            "confidence": 0.0,
            "timestamp": datetime.now().isoformat(),
            "entry_price": 0.0,
            "stop_loss": 0.0,
            "take_profit": 0.0,
            "risk_reward_ratio": 0.0,
            "model_votes": {},
            "reasoning": [reason],
            "top_features": [],
            "timeframe": "unknown",
            "ensemble_probabilities": {"SELL": 0.0, "HOLD": 1.0, "BUY": 0.0},
            "timeframe_analysis": [],
            "final_aggregation": {
                "global_score": 0.0,
                "conflict_ratio": 0.0,
                "timeframe_weights": {},
                "gate_reasons": [],
                "timeframe_order": [],
            },
        }
