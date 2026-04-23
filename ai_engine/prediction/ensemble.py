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

from ..calibration.artifacts import load_calibration_artifact, load_threshold_artifact
from ..calibration.calibrator import apply_calibrator, load_calibrator
from ..features.feature_engineer import FeatureEngineer
from ..features.feature_scaler import FeatureScaler
from ..governance.decision_governor import DecisionGovernor
from ..models.xgboost_model import XGBoostModel
from ..models.lightgbm_model import LightGBMModel
from strategy.regime_detector import RegimeDetector

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
        min_confidence: float = 0.55,
        min_agreement: int = 1,
        risk_reward_ratio: float = 2.0,
        pip_size: float | None = None,
        timeframe_weights: dict[str, float] | None = None,
        model_weight: float = 0.50,
        indicator_weight: float = 0.20,
        sentiment_weight: float = 0.15,
        mirofish_weight: float = 0.15,
        decision_threshold: float = 0.15,
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
        
        # Basis-Gewichte speichern (werden dynamisch normalisiert pro Vorhersage)
        self.model_weight = float(np.clip(model_weight, 0.0, 1.0))
        self.indicator_weight = float(np.clip(indicator_weight, 0.0, 1.0))
        total_weight = self.model_weight + self.indicator_weight
        if total_weight <= 0:
            self.model_weight = 0.7
            self.indicator_weight = 0.3
            total_weight = 1.0
        self.model_weight /= total_weight
        self.indicator_weight /= total_weight
        self.sentiment_weight = float(np.clip(sentiment_weight, 0.0, 1.0))
        self.mirofish_weight = float(np.clip(mirofish_weight, 0.0, 1.0))

        self.decision_threshold = float(max(0.01, decision_threshold))
        self.max_conflict_ratio = float(np.clip(max_conflict_ratio, 0.0, 1.0))
        self.strict_high_tf_alignment = strict_high_tf_alignment

        self._xgboost = XGBoostModel()
        self._lightgbm = LightGBMModel()
        self._scaler = FeatureScaler()
        self._feature_engineer = FeatureEngineer()
        self._regime_detector = RegimeDetector()
        self._decision_governor = DecisionGovernor(
            default_min_confidence=self.min_confidence,
            default_max_conflict_ratio=self.max_conflict_ratio,
        )
        self._model_calibrators: dict[str, Any] = {}
        self._threshold_artifact = (
            self._decision_governor.build_default_threshold_artifact()
        )

        self._models_loaded = False

        # Persistent thread pool for parallel timeframe analysis.
        # Avoids creating/destroying a pool on every predict() call.
        self._executor = ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="ensemble-tf"
        )

    def close(self) -> None:
        """Shutdown the persistent thread pool. Call on system shutdown."""
        executor = getattr(self, "_executor", None)
        if executor is not None:
            try:
                executor.shutdown(wait=False)
            except Exception:
                pass
            self._executor = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

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

        self._load_governance_artifacts()

        self._models_loaded = loaded_count > 0
        logger.info("%d/2 Modelle geladen", loaded_count)
        return self._models_loaded

    def _load_governance_artifacts(self) -> None:
        self._model_calibrators = {}
        self._threshold_artifact = (
            self._decision_governor.build_default_threshold_artifact()
        )

        calibration_path = os.path.join(self.saved_models_dir, "calibration.json")
        if os.path.exists(calibration_path):
            try:
                calibration_artifact = load_calibration_artifact(calibration_path)
                for model_name, payload in calibration_artifact.get(
                    "models", {}
                ).items():
                    calibrator_name = payload.get("calibrator_path")
                    if not calibrator_name:
                        continue
                    calibrator_path = os.path.join(
                        self.saved_models_dir,
                        os.path.basename(str(calibrator_name)),
                    )
                    if os.path.exists(calibrator_path):
                        self._model_calibrators[model_name] = load_calibrator(
                            calibrator_path
                        )
                logger.info(
                    "Governance calibration loaded for %d model(s)",
                    len(self._model_calibrators),
                )
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("Calibration artifact load failed: %s", exc)

        threshold_path = os.path.join(self.saved_models_dir, "thresholds.json")
        if os.path.exists(threshold_path):
            try:
                threshold_artifact = load_threshold_artifact(threshold_path)
                self._threshold_artifact = self._merge_threshold_models(
                    threshold_artifact
                )
                logger.info("Threshold artifact loaded")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Threshold artifact load failed: %s", exc)

    def _merge_threshold_models(self, artifact: dict[str, Any]) -> dict[str, Any]:
        if "thresholds" in artifact:
            merged = dict(artifact)
            merged.setdefault("defaults", {})
            merged["defaults"].setdefault(
                "max_conflict_ratio",
                self.max_conflict_ratio,
            )
            return merged

        models = artifact.get("models", {})
        if not models:
            return self._decision_governor.build_default_threshold_artifact()

        merged = self._decision_governor.build_default_threshold_artifact()
        merged["source"] = {
            "model_name": "merged-runtime-thresholds",
            "model_count": len(models),
        }

        for action in ("SELL", "BUY", "HOLD"):
            entries = [
                model_payload.get("defaults", {}).get(action)
                for model_payload in models.values()
                if model_payload.get("defaults", {}).get(action)
            ]
            if entries:
                merged["defaults"][action] = {
                    "action": action,
                    "min_confidence": float(
                        np.mean(
                            [entry.get("min_confidence", 0.0) for entry in entries]
                        )
                    ),
                    "min_margin": float(
                        np.mean([entry.get("min_margin", 0.0) for entry in entries])
                    ),
                }

        regime_keys = {
            regime
            for model_payload in models.values()
            for regime in model_payload.get("thresholds", {}).keys()
        }
        for regime in regime_keys:
            regime_table: dict[str, Any] = {}
            for action in ("SELL", "BUY"):
                entries = [
                    model_payload.get("thresholds", {}).get(regime, {}).get(action)
                    for model_payload in models.values()
                    if model_payload.get("thresholds", {}).get(regime, {}).get(action)
                ]
                if entries:
                    regime_table[action] = {
                        "action": action,
                        "min_confidence": float(
                            np.mean(
                                [entry.get("min_confidence", 0.0) for entry in entries]
                            )
                        ),
                        "min_margin": float(
                            np.mean([entry.get("min_margin", 0.0) for entry in entries])
                        ),
                    }
            if regime_table:
                merged["thresholds"][regime] = regime_table

        return merged

    def predict(
        self,
        candle_data: dict[str, pd.DataFrame],
        primary_timeframe: str = "5m",
        sentiment_data: dict[str, float] | None = None,
        mirofish_signal: dict[str, Any] | None = None,
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

        failed_timeframes: list[str] = []

        if len(analyzable) > 1:
            # Use persistent executor (created in __init__) to avoid pool churn.
            executor = getattr(self, "_executor", None)
            if executor is None:
                # Defensive fallback if close() was called previously.
                self._executor = ThreadPoolExecutor(
                    max_workers=4, thread_name_prefix="ensemble-tf"
                )
                executor = self._executor

            futures = {executor.submit(_analyze, item): item[0] for item in analyzable}
            for future in futures:
                tf = futures[future]
                try:
                    analyses.append(future.result())
                except Exception as exc:
                    logger.warning("Analyse fehlgeschlagen fuer %s: %s", tf, exc)
                    failed_timeframes.append(tf)
                    # Explicit NaN marker so aggregation can account for the gap
                    # instead of silently dropping the timeframe.
                    analyses.append({
                        "timeframe": tf,
                        "failed": True,
                        "error": str(exc),
                        "action": "HOLD",
                        "confidence": float("nan"),
                        "model_score": float("nan"),
                        "indicator_score": float("nan"),
                        "model_votes": {},
                        "feature_names": [],
                        "_latest_features": None,
                    })
        else:
            for item in analyzable:
                try:
                    analyses.append(_analyze(item))
                except Exception as exc:
                    logger.warning("Analyse fehlgeschlagen fuer %s: %s", item[0], exc)
                    failed_timeframes.append(item[0])
                    analyses.append({
                        "timeframe": item[0],
                        "failed": True,
                        "error": str(exc),
                        "action": "HOLD",
                        "confidence": float("nan"),
                        "model_score": float("nan"),
                        "indicator_score": float("nan"),
                        "model_votes": {},
                        "feature_names": [],
                        "_latest_features": None,
                    })

        # If every timeframe failed, abort early so the caller sees the error.
        if failed_timeframes and len(failed_timeframes) == len(analyzable):
            return self._empty_signal(
                f"Alle Timeframes fehlgeschlagen: {', '.join(failed_timeframes)}"
            )

        # Higher-timeframe failure: log warning but continue with available data
        # instead of aborting entirely. This prevents the system from blocking
        # all trades when a single higher TF is temporarily unavailable.
        critical_failed = [
            tf for tf in failed_timeframes if tf in self.HIGHER_TIMEFRAMES
        ]
        if critical_failed:
            logger.warning(
                "Higher-TF-Analyse fehlgeschlagen fuer: %s -- weiter mit verfuegbaren Daten",
                ", ".join(critical_failed),
            )

        # Drop NaN-only entries before aggregation; aggregation operates on
        # successful analyses but `failed_timeframes` is reflected in metadata.
        analyses = [a for a in analyses if not a.get("failed")]

        if not analyses:
            return self._empty_signal("Keine analysierbaren Timeframes")

        aggregation = self._aggregate_decisions(
            analyses,
            sentiment_data,
            mirofish_signal,
        )

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
                "threshold_source": aggregation.get("threshold_source", "defaults"),
                "gate_decision": aggregation.get("gate_decision", "pass"),
                "regime": aggregation.get("regime", "ranging"),
                "decision_audit": aggregation.get("decision_audit", {}),
                "timeframe_order": timeframe_order,
                "sentiment_impact": aggregation.get("sentiment_impact", 0.0),
                "mirofish_impact": aggregation.get("mirofish_impact", 0.0),
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

        regime_state = self._regime_detector.detect(df)
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
                calibrator = self._model_calibrators.get(model_name)
                if calibrator is not None:
                    probs = apply_calibrator(calibrator, np.asarray([probs]))[0]
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
        disagreement_reason: str | None = None
        if model_action != "HOLD" and len(model_votes) >= 2 and agreement_count < self.min_agreement:
            disagreement_reason = (
                f"model_disagreement {agreement_count} < min_agreement {self.min_agreement}"
            )
            logger.debug("Model disagreement on %s: forcing HOLD", timeframe)

        indicator_score, indicator_components, indicator_snapshot = self._calculate_indicator_score(df)

        model_signed_score = self._action_to_sign(model_action) * model_confidence
        combined_score = (self.model_weight * model_signed_score) + (
            self.indicator_weight * indicator_score
        )

        tf_threshold = max(0.08, self.decision_threshold * 0.5)
        action = self._score_to_action(combined_score, threshold=tf_threshold)
        confidence = float(min(1.0, abs(combined_score)))
        if disagreement_reason is not None:
            combined_score = 0.0
            action = "HOLD"
            confidence = 0.0

        reasoning = self._generate_tf_reasoning(
            features=df.iloc[-1],
            votes=model_votes,
            final_action=action,
        )
        if disagreement_reason is not None:
            reasoning.insert(0, disagreement_reason)

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
            "regime": regime_state.regime.value,
            "regime_confidence": round(float(regime_state.confidence), 6),
            "ensemble_probabilities": {
                "SELL": float(ensemble_probs[0]),
                "HOLD": float(ensemble_probs[1]),
                "BUY": float(ensemble_probs[2]),
            },
            "reasoning": reasoning,
            "feature_names": feature_names,
            "_latest_features": df.iloc[-1],
        }

    def _aggregate_timeframe_decisions(self, analyses: list[dict[str, Any]]) -> dict[str, Any]:
        """Backward-compatible wrapper for tests and older call sites."""
        normalized: list[dict[str, Any]] = []
        for analysis in analyses:
            model_action = str(analysis.get("model_action") or analysis.get("action") or "HOLD")
            model_confidence = analysis.get("model_confidence")
            if model_confidence is None:
                model_confidence = abs(float(analysis.get("combined_score", 0.0)))
            normalized.append({
                "timeframe": analysis.get("timeframe", "unknown"),
                "model_action": model_action,
                "model_confidence": float(model_confidence),
                "indicator_score": float(analysis.get("indicator_score", 0.0)),
                "regime": str(analysis.get("regime", "ranging")),
            })
        return self._aggregate_decisions(normalized, sentiment_data=None, mirofish_signal=None)

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

    def _aggregate_decisions(
        self,
        analyses: list[dict[str, Any]],
        sentiment_data: dict[str, float] | None,
        mirofish_signal: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """
        Aggregiert Technicals (Multi-TF), Sentiment und MiroFish (Schwarm).
        """
        # 1. Technical Score über alle Timeframes
        weight_map = self._normalize_timeframe_weights([a["timeframe"] for a in analyses])

        technical_score = 0.0
        # Weighted mean of signed model confidences across TFs -- used as the
        # ensemble's own confidence signal (independent of indicator contribution).
        weighted_model_signal = 0.0

        for analysis in analyses:
            tf = analysis["timeframe"]
            tf_weight = weight_map.get(tf, 0.0)

            mod_action = analysis["model_action"]
            mod_conf = analysis["model_confidence"]
            mod_score = self._action_to_sign(mod_action) * mod_conf
            ind_score = analysis["indicator_score"]

            # Use the same model/indicator split that was configured on __init__,
            # not hardcoded 0.6/0.4 -- otherwise per-TF and aggregate weights
            # disagree and confidence gets arbitrarily diluted.
            tf_score = (self.model_weight * mod_score) + (self.indicator_weight * ind_score)
            technical_score += tf_weight * tf_score
            weighted_model_signal += tf_weight * mod_score

        # 2. Sentiment Score (News + Fear/Greed)
        sentiment_score = 0.0
        has_sentiment = False
        if sentiment_data:
            # Erwartet: "news_score" (-1 bis 1), "fear_greed_index" (0 bis 100)
            # Fear & Greed bei Gold: Hohe Angst (niedriger Index) oft Bullish für Gold (Safe Haven)
            news = float(sentiment_data.get("news_score", 0.0))
            fg_index = float(sentiment_data.get("fear_greed_index", 50.0))
            
            # Normalize FG: 0-20 (Fear) -> +1.0, 80-100 (Greed) -> -0.5 (Mean Reversion?)
            # Annahme für Gold: Angst treibt Preis.
            fg_score = 0.0
            if fg_index < 25:
                fg_score = 0.8   # Extreme Fear -> Buy Gold
            elif fg_index > 75:
                fg_score = -0.3  # Extreme Greed -> Caution/Sell
            
            sentiment_score = (0.7 * news) + (0.3 * fg_score)
            has_sentiment = True

        # 3. MiroFish Score (Schwarm)
        mirofish_score = 0.0
        has_mirofish = False
        if mirofish_signal:
            mf_action = mirofish_signal.get("action", "HOLD")
            mf_conf = float(mirofish_signal.get("confidence", 0.0))
            mirofish_score = self._action_to_sign(mf_action) * mf_conf
            has_mirofish = True

        # 4. Globale Gewichtung & Normalisierung
        active_weights = {
            "technical": self.model_weight + self.indicator_weight, # Basis Technicals
            "sentiment": self.sentiment_weight if has_sentiment else 0.0,
            "mirofish": self.mirofish_weight if has_mirofish else 0.0
        }
        total_w = sum(active_weights.values())
        if total_w <= 0:
            total_w = 1.0
        
        norm_w = {k: v / total_w for k, v in active_weights.items()}
        
        global_score = (
            (norm_w["technical"] * technical_score) +
            (norm_w["sentiment"] * sentiment_score) +
            (norm_w["mirofish"] * mirofish_score)
        )

        # Entscheidung
        preliminary_action = self._score_to_action(global_score, self.decision_threshold)
        conflict_ratio = self._compute_conflict_ratio(analyses)

        # Compute base confidence first, then apply soft penalties
        if preliminary_action == "HOLD":
            confidence = float(min(1.0, abs(global_score)))
        else:
            target_sign = self._action_to_sign(preliminary_action)
            directional = max(0.0, target_sign * weighted_model_signal)
            confidence = float(min(1.0, max(directional, abs(global_score))))

        logger.info(
            "Gate-Debug: preliminary=%s, score=%.4f, base_confidence=%.4f, "
            "model_signal=%.4f, conflict=%.4f",
            preliminary_action, global_score, confidence,
            weighted_model_signal, conflict_ratio,
        )

        governance_regime = self._resolve_governance_regime(analyses, weight_map)
        higher_tf_aligned = True
        higher_tf_detail = "alignment_disabled"
        if preliminary_action != "HOLD" and self.strict_high_tf_alignment:
            higher_tf_aligned, higher_tf_detail = self._check_higher_tf_alignment(
                analyses,
                preliminary_action,
            )

        audit = self._decision_governor.evaluate(
            preliminary_action=preliminary_action,
            confidence=confidence,
            global_score=global_score,
            conflict_ratio=conflict_ratio,
            regime=governance_regime,
            threshold_artifact=self._threshold_artifact,
            higher_tf_aligned=higher_tf_aligned,
            higher_tf_detail=higher_tf_detail,
            specialist_signal=None,
        )

        probabilities = self._global_score_to_probabilities(
            global_score,
            hold_bias=(audit.final_action == "HOLD"),
        )

        return {
            "action": audit.final_action,
            "confidence": audit.final_confidence,
            "global_score": round(float(global_score), 6),
            "conflict_ratio": round(float(conflict_ratio), 6),
            "regime": governance_regime,
            "timeframe_weights": {k: round(float(v), 6) for k, v in weight_map.items()},
            "sentiment_impact": round(norm_w["sentiment"] * sentiment_score, 4),
            "mirofish_impact": round(norm_w["mirofish"] * mirofish_score, 4),
            "gate_reasons": audit.gate_reasons,
            "threshold_source": audit.threshold_source,
            "gate_decision": audit.gate_decision.value,
            "decision_audit": audit.to_dict(),
            "ensemble_probabilities": probabilities,
        }

    def _resolve_governance_regime(
        self,
        analyses: list[dict[str, Any]],
        weight_map: dict[str, float],
    ) -> str:
        regime_weights: dict[str, float] = {}
        for analysis in analyses:
            regime = str(analysis.get("regime", "ranging"))
            timeframe = str(analysis.get("timeframe", ""))
            regime_weights[regime] = regime_weights.get(regime, 0.0) + weight_map.get(
                timeframe,
                0.0,
            )
        if not regime_weights:
            return "ranging"
        return max(regime_weights.items(), key=lambda item: item[1])[0]

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
            "regime": analysis.get("regime"),
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
        
        if abs(aggregation.get("sentiment_impact", 0)) > 0.05:
            reasons.append(f"Sentiment Impact: {aggregation['sentiment_impact']:+.2f}")
        
        if abs(aggregation.get("mirofish_impact", 0)) > 0.05:
            reasons.append(f"MiroFish Impact: {aggregation['mirofish_impact']:+.2f}")

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

    def _generate_tf_reasoning(
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
                "threshold_source": "defaults",
                "gate_decision": "pass",
                "regime": "ranging",
                "decision_audit": {},
                "timeframe_order": [],
            },
        }
