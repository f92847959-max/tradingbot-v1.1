"""Runtime contract for the existing-AI autonomy decision head."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

import joblib
import numpy as np
import pandas as pd

from ai_engine.features.feature_scaler import FeatureScaler
from ai_engine.training.decision_snapshot_capture import ACTIONS, LABEL_TO_ACTION
from ai_engine.training.model_versioning import get_specialist_root

DECISION_HEAD_NAME = "decision_head"
MODEL_FILENAME = "decision_head_model.pkl"
SCALER_FILENAME = "decision_head_scaler.pkl"
FEATURE_MANIFEST_FILENAME = "decision_head_manifest.json"


@dataclass(frozen=True)
class DecisionHeadPrediction:
    action: str
    confidence: float
    probabilities: dict[str, float]
    available: bool = True
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionHeadRuntime:
    """Optional runtime loader for the autonomy decision head."""

    def __init__(
        self,
        *,
        saved_models_dir: str = "ai_engine/saved_models",
        specialist_name: str = DECISION_HEAD_NAME,
        enabled: bool = True,
    ) -> None:
        self.saved_models_dir = saved_models_dir
        self.specialist_name = specialist_name
        self.enabled = enabled
        self._model = None
        self._scaler: FeatureScaler | None = None
        self._feature_names: list[str] = []

    def load(self) -> bool:
        if not self.enabled:
            return False
        root = get_specialist_root(self.saved_models_dir, self.specialist_name)
        production_path = f"{root}/production.json"
        try:
            import json

            with open(production_path, "r", encoding="utf-8") as handle:
                pointer = json.load(handle)
            version_dir = pointer.get("path") or f"{root}/{pointer.get('version_dir', '')}"
            with open(f"{version_dir}/{FEATURE_MANIFEST_FILENAME}", "r", encoding="utf-8") as handle:
                manifest = json.load(handle)
            scaler = FeatureScaler()
            scaler.load(f"{version_dir}/{SCALER_FILENAME}")
            payload = joblib.load(f"{version_dir}/{MODEL_FILENAME}")
            self._model = payload["model"]
            self._scaler = scaler
            self._feature_names = list(manifest["feature_names"])
        except Exception:
            self._model = None
            self._scaler = None
            self._feature_names = []
        return self._model is not None

    def predict_from_signal(self, signal: Mapping[str, Any]) -> DecisionHeadPrediction:
        if self._model is None and not self.load():
            return DecisionHeadPrediction(
                action=str(signal.get("action", "HOLD")),
                confidence=float(signal.get("confidence", 0.0)),
                probabilities={str(signal.get("action", "HOLD")): float(signal.get("confidence", 0.0))},
                available=False,
                reason="decision_head_unavailable",
            )
        assert self._scaler is not None
        features = _features_from_signal(signal, self._feature_names)
        scaled = self._scaler.transform(pd.DataFrame([features]))[
            self._feature_names
        ].values.astype(np.float32)
        probabilities = np.asarray(self._model.predict_proba(scaled), dtype=float)[0]
        if len(probabilities) != len(ACTIONS):
            padded = np.zeros(len(ACTIONS), dtype=float)
            padded[: len(probabilities)] = probabilities
            probabilities = padded
        label = int(np.argmax(probabilities))
        action = LABEL_TO_ACTION.get(label, "HOLD")
        return DecisionHeadPrediction(
            action=action,
            confidence=float(probabilities[label]),
            probabilities={
                LABEL_TO_ACTION[idx]: round(float(value), 6)
                for idx, value in enumerate(probabilities)
            },
            available=True,
            reason="decision_head_prediction",
        )


def apply_autonomy_rollout(
    champion_signal: Mapping[str, Any],
    candidate_prediction: DecisionHeadPrediction | Mapping[str, Any] | None,
    *,
    mode: str = "shadow",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select champion/candidate according to the staged rollout mode."""
    champion = dict(champion_signal)
    candidate = _prediction_payload(candidate_prediction)
    champion_action = str(champion.get("action", "HOLD"))
    candidate_action = str(candidate.get("action", champion_action))
    candidate_available = bool(candidate.get("available", False))
    selected_source = "champion"

    selected = dict(champion)
    normalized_mode = str(mode or "shadow")
    if candidate_available and normalized_mode == "agreement_guarded":
        if candidate_action == champion_action:
            selected_source = "candidate_agreement"
            selected["action"] = candidate_action
            selected["confidence"] = min(
                float(selected.get("confidence", 0.0)),
                float(candidate.get("confidence", 0.0)),
            )
    elif candidate_available and normalized_mode == "primary_with_challenger":
        selected_source = "candidate"
        selected["action"] = candidate_action
        selected["confidence"] = float(candidate.get("confidence", 0.0))

    metadata = {
        "schema_version": 1,
        "mode": normalized_mode,
        "selected_source": selected_source,
        "champion": {
            "action": champion_action,
            "confidence": float(champion.get("confidence", 0.0)),
        },
        "candidate": candidate,
        "disagreement": candidate_available and candidate_action != champion_action,
        "guard_bypass_count": 0,
    }
    selected["autonomy_rollout"] = metadata
    return selected, metadata


def _features_from_signal(signal: Mapping[str, Any], feature_names: list[str]) -> dict[str, float]:
    final_aggregation = signal.get("final_aggregation") or {}
    probabilities = signal.get("ensemble_probabilities") or {}
    all_features = {
        "confidence": float(signal.get("confidence", 0.0)),
        "trade_score": float(signal.get("trade_score", 0.0) or 0.0),
        "global_score": float(final_aggregation.get("global_score", 0.0) or 0.0),
        "conflict_ratio": float(final_aggregation.get("conflict_ratio", 0.0) or 0.0),
        "prob_sell": float(probabilities.get("SELL", 0.0) or 0.0),
        "prob_hold": float(probabilities.get("HOLD", 0.0) or 0.0),
        "prob_buy": float(probabilities.get("BUY", 0.0) or 0.0),
    }
    return {name: all_features.get(name, 0.0) for name in feature_names}


def _prediction_payload(
    prediction: DecisionHeadPrediction | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if prediction is None:
        return {
            "action": "HOLD",
            "confidence": 0.0,
            "probabilities": {},
            "available": False,
            "reason": "candidate_missing",
        }
    if isinstance(prediction, DecisionHeadPrediction):
        return prediction.to_dict()
    return dict(prediction)
