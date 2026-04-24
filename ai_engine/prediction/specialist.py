"""Runtime adapter for optional specialist overlay predictions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ..training.specialist_pipeline import (
    DEFAULT_SPECIALIST_NAME,
    SpecialistBundle,
    load_specialist_bundle,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpecialistPrediction:
    name: str
    available: bool
    action: str = "HOLD"
    confidence: float = 0.0
    score: float = 0.0
    reason: str = ""
    probabilities: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "action": self.action,
            "confidence": float(self.confidence),
            "score": float(self.score),
            "reason": self.reason,
            "probabilities": dict(self.probabilities),
        }

    @classmethod
    def noop(cls, name: str, reason: str) -> "SpecialistPrediction":
        return cls(
            name=name,
            available=False,
            action="HOLD",
            confidence=0.0,
            score=0.0,
            reason=reason,
            probabilities={"SELL": 0.0, "HOLD": 1.0, "BUY": 0.0},
        )


class SpecialistRuntime:
    """Load and score the isolated specialist model as a no-op-safe overlay."""

    def __init__(
        self,
        *,
        saved_models_dir: str = "ai_engine/saved_models",
        specialist_name: str = DEFAULT_SPECIALIST_NAME,
        enabled: bool = True,
        min_confidence: float = 0.55,
        min_score: float = 0.10,
    ) -> None:
        self.saved_models_dir = saved_models_dir
        self.specialist_name = specialist_name
        self.enabled = enabled
        self.min_confidence = float(min_confidence)
        self.min_score = float(min_score)
        self._bundle: SpecialistBundle | None = None
        self._last_reason = "specialist_disabled" if not enabled else "specialist_unloaded"

    @property
    def available(self) -> bool:
        return self._bundle is not None

    def load(self) -> bool:
        """Load the promoted specialist bundle if available."""
        if not self.enabled:
            self._bundle = None
            self._last_reason = "specialist_disabled"
            return False

        try:
            self._bundle = load_specialist_bundle(
                self.saved_models_dir,
                specialist_name=self.specialist_name,
            )
            self._last_reason = "ready"
            return True
        except FileNotFoundError:
            self._bundle = None
            self._last_reason = "specialist_artifacts_missing"
            return False
        except ValueError as exc:
            self._bundle = None
            self._last_reason = str(exc)
            logger.warning("Specialist load failed: %s", exc)
            return False

    def predict_from_feature_frame(
        self,
        feature_df: pd.DataFrame,
    ) -> SpecialistPrediction:
        """Score the latest row of a feature frame with the specialist model."""
        if feature_df.empty:
            return SpecialistPrediction.noop(
                self.specialist_name,
                "empty_specialist_feature_frame",
            )

        if self._bundle is None and not self.load():
            return SpecialistPrediction.noop(self.specialist_name, self._last_reason)

        assert self._bundle is not None
        missing = [
            name for name in self._bundle.feature_names
            if name not in feature_df.columns
        ]
        if missing:
            return SpecialistPrediction.noop(
                self.specialist_name,
                f"feature_block_missing:{','.join(missing[:3])}",
            )

        latest = feature_df.iloc[[-1]].copy()
        scaled = self._bundle.scaler.transform(latest)
        X_latest = scaled[self._bundle.feature_names].values.astype(np.float32)
        probabilities = self._bundle.model.predict(X_latest)[0]

        sell_prob = float(probabilities[0])
        hold_prob = float(probabilities[1])
        buy_prob = float(probabilities[2])
        score = buy_prob - sell_prob
        confidence = max(sell_prob, hold_prob, buy_prob)

        action = "HOLD"
        reason = "specialist_neutral"
        if score >= self.min_score and confidence >= self.min_confidence:
            action = "BUY"
            reason = f"{self.specialist_name}_confirm_buy"
        elif score <= -self.min_score and confidence >= self.min_confidence:
            action = "SELL"
            reason = f"{self.specialist_name}_confirm_sell"

        return SpecialistPrediction(
            name=self.specialist_name,
            available=True,
            action=action,
            confidence=round(float(confidence), 6),
            score=round(float(score), 6),
            reason=reason,
            probabilities={
                "SELL": sell_prob,
                "HOLD": hold_prob,
                "BUY": buy_prob,
            },
        )
