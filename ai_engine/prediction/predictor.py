"""
AI Predictor -- Einfache Schnittstelle fuer andere Module.

Nutzt ausschliesslich das XGBoost + LightGBM Ensemble.
Laeuft komplett auf CPU, kostenlos, keine API-Aufrufe.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from inspect import isawaitable
from typing import Any

import pandas as pd


logger = logging.getLogger(__name__)


class AIPredictor:
    """
    Einheitliche Schnittstelle fuer KI-Vorhersagen.

    Nutzt XGBoost (55%) + LightGBM (45%) Ensemble.
    """

    def __init__(
        self,
        saved_models_dir: str = "ai_engine/saved_models",
        min_confidence: float = 0.70,
        risk_reward_ratio: float = 2.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.saved_models_dir = saved_models_dir
        self._is_loaded = False
        self._last_signal: dict[str, Any] | None = None

        from .ensemble import EnsemblePredictor

        self._predictor = EnsemblePredictor(
            saved_models_dir=saved_models_dir,
            weights=weights,
            min_confidence=min_confidence,
            risk_reward_ratio=risk_reward_ratio,
        )
        logger.info(
            "AIPredictor initialisiert (Engine: Ensemble, Modelle: %s)",
            saved_models_dir,
        )

    def _empty_signal(self, reason: str) -> dict[str, Any]:
        return self._predictor._empty_signal(reason)

    def load(self) -> bool:
        """Laedt die trainierten Modelle."""
        self._is_loaded = bool(self._predictor.load_models())
        if self._is_loaded:
            logger.info("AIPredictor bereit (Ensemble geladen)")
        else:
            logger.warning("Keine trainierten Modelle gefunden in %s", self.saved_models_dir)
        return self._is_loaded

    async def predict(
        self,
        candle_data: dict[str, pd.DataFrame] | None = None,
        data_provider: Any | None = None,
        primary_timeframe: str = "5m",
        sentiment_data: dict[str, float] | None = None,
        mirofish_signal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Erzeugt eine Trading-Vorhersage.

        Bei Fehlern wird immer ein HOLD-Signal geliefert.
        """
        if not self._is_loaded and not self.load():
            return self._empty_signal("Keine trainierten Modelle - Training noetig!")

        if candle_data is None and data_provider is not None:
            try:
                if hasattr(data_provider, "get_all_timeframes"):
                    maybe_data = data_provider.get_all_timeframes(count=5000)
                elif hasattr(data_provider, "get_multi_timeframe_data"):
                    maybe_data = data_provider.get_multi_timeframe_data(
                        timeframes=["5m", "15m", "1h"],
                        count=None,
                    )
                else:
                    maybe_data = None

                if isawaitable(maybe_data):
                    candle_data = await maybe_data
                else:
                    candle_data = maybe_data
            except Exception as exc:
                logger.error("Daten laden fehlgeschlagen: %s", exc)
                return self._empty_signal(f"Daten-Fehler: {exc}")

        if candle_data is None:
            return self._empty_signal("Keine Daten verfuegbar")

        try:
            signal = self._predictor.predict(
                candle_data,
                primary_timeframe,
                sentiment_data=sentiment_data,
                mirofish_signal=mirofish_signal,
            )
            self._last_signal = signal
            return signal
        except Exception as exc:
            logger.exception("Vorhersage fehlgeschlagen: %s", exc)
            return self._empty_signal(f"Vorhersage-Fehler: {exc}")

    def get_last_signal(self) -> dict[str, Any] | None:
        """Gibt das letzte Signal zurueck."""
        return self._last_signal

    def get_model_info(self) -> dict[str, Any]:
        """Gibt Modell-Informationen zurueck."""
        meta_path = os.path.join(self.saved_models_dir, "model_metadata.json")
        if not os.path.exists(meta_path):
            return {"status": "not_trained", "message": "Kein trainiertes Modell gefunden"}

        try:
            with open(meta_path, "r", encoding="utf-8") as file:
                metadata = json.load(file)
            return {
                "status": "trained",
                "engine": "ensemble_xgb_lgbm",
                "training_date": metadata.get("training_date", "unbekannt"),
                "timeframe": metadata.get("timeframe", "unbekannt"),
                "n_features": metadata.get("n_features", 0),
                "n_samples": metadata.get("n_samples_total", 0),
                "xgboost_accuracy": metadata.get("xgboost_accuracy"),
                "xgboost_f1": metadata.get("xgboost_f1"),
                "lightgbm_accuracy": metadata.get("lightgbm_accuracy"),
                "lightgbm_f1": metadata.get("lightgbm_f1"),
                "training_duration": metadata.get("training_duration_seconds"),
            }
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Metadata lesen fehlgeschlagen: %s", exc)
            return {"status": "error", "message": str(exc)}

    def needs_retraining(self, retrain_interval_days: int = 7) -> bool:
        """Prueft ob ein Retraining noetig ist."""
        meta_path = os.path.join(self.saved_models_dir, "model_metadata.json")
        if not os.path.exists(meta_path):
            return True

        try:
            with open(meta_path, "r", encoding="utf-8") as file:
                metadata = json.load(file)
            training_date_str = metadata.get("training_date")
            if not training_date_str:
                return True
            training_date = datetime.fromisoformat(training_date_str)
            if training_date.tzinfo is None:
                training_date = training_date.replace(tzinfo=timezone.utc)
            days_since = (datetime.now(timezone.utc) - training_date).days
            return days_since >= retrain_interval_days
        except (OSError, json.JSONDecodeError, ValueError):
            return True

    @property
    def is_ready(self) -> bool:
        return self._is_loaded
