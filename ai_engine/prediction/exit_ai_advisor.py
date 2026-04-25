"""Runtime loader and bounded recommendation contract for Exit-AI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ai_engine.training.exit_ai_labels import (
    EXIT_AI_ACTIONS,
    ExitSnapshotBuilder,
    LABEL_TO_ACTION,
)
from ai_engine.training.exit_ai_pipeline import (
    DEFAULT_EXIT_AI_NAME,
    load_exit_ai_bundle,
)


@dataclass(frozen=True)
class ExitAIRecommendation:
    """A bounded runtime recommendation from the Exit-AI specialist."""

    action: str
    confidence: float
    reason: str
    proposed_stop_loss: float | None = None
    close_fraction: float = 0.0
    no_op: bool = False
    baseline_context: dict[str, Any] = field(default_factory=dict)
    raw_probabilities: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExitAIAdvisor:
    """Load Exit-AI artifacts and emit safe runtime recommendations."""

    def __init__(
        self,
        *,
        saved_models_dir: str = "ai_engine/saved_models",
        specialist_name: str = DEFAULT_EXIT_AI_NAME,
        enabled: bool = True,
    ) -> None:
        self.saved_models_dir = saved_models_dir
        self.specialist_name = specialist_name
        self.enabled = enabled
        self._bundle = None
        self._builder = ExitSnapshotBuilder()

    @property
    def is_available(self) -> bool:
        return self._bundle is not None

    def load(self) -> bool:
        if not self.enabled:
            return False
        try:
            self._bundle = load_exit_ai_bundle(
                self.saved_models_dir,
                specialist_name=self.specialist_name,
            )
        except Exception:
            self._bundle = None
        return self._bundle is not None

    def recommend(
        self,
        snapshot: dict[str, Any],
        *,
        enabled: bool | None = None,
    ) -> ExitAIRecommendation:
        """Return a bounded recommendation or a no-op fallback."""
        if enabled is False or (enabled is None and not self.enabled):
            return self._noop("advisor_disabled")
        if self._bundle is None and not self.load():
            return self._noop("artifacts_unavailable")

        try:
            sample = self._builder.build_snapshot(snapshot)
            feature_frame = pd.DataFrame([sample.features])
            scaled = self._bundle.scaler.transform(feature_frame)[
                self._bundle.feature_names
            ].values.astype(np.float32)
            probabilities = np.asarray(
                self._bundle.model.predict_proba(scaled),
                dtype=float,
            )
            if probabilities.shape[1] != len(EXIT_AI_ACTIONS):
                padded = np.zeros((1, len(EXIT_AI_ACTIONS)), dtype=float)
                padded[:, : probabilities.shape[1]] = probabilities
                probabilities = padded

            scores = probabilities[0]
            label = int(np.argmax(scores))
            action = LABEL_TO_ACTION[label]
            confidence = float(scores[label])
            if action not in EXIT_AI_ACTIONS:
                return self._noop("unsafe_action_predicted")

            raw_probabilities = {
                name: round(float(scores[idx]), 6)
                for idx, name in LABEL_TO_ACTION.items()
            }

            if action == "TIGHTEN_SL":
                proposed_stop = sample.baseline_context.get("baseline_trailing_sl")
                if not self._is_monotonic_tightening(
                    direction=str(snapshot.get("direction", "")),
                    current_stop_loss=float(snapshot.get("current_stop_loss", 0.0)),
                    proposed_stop_loss=proposed_stop,
                ):
                    return self._noop(
                        "risk_widening_rejected",
                        baseline_context=sample.baseline_context,
                        raw_probabilities=raw_probabilities,
                    )
                return ExitAIRecommendation(
                    action=action,
                    confidence=confidence,
                    reason=str(sample.baseline_context.get("baseline_trailing_reason", "")),
                    proposed_stop_loss=float(proposed_stop),
                    baseline_context=sample.baseline_context,
                    raw_probabilities=raw_probabilities,
                )

            if action == "PARTIAL_CLOSE":
                close_fraction = float(
                    sample.baseline_context.get("baseline_partial_close_fraction", 0.0)
                )
                if close_fraction <= 0:
                    return self._noop(
                        "partial_close_unavailable",
                        baseline_context=sample.baseline_context,
                        raw_probabilities=raw_probabilities,
                    )
                return ExitAIRecommendation(
                    action=action,
                    confidence=confidence,
                    reason=str(
                        sample.baseline_context.get("baseline_partial_close_reason", "")
                    ),
                    close_fraction=close_fraction,
                    baseline_context=sample.baseline_context,
                    raw_probabilities=raw_probabilities,
                )

            if action == "FULL_EXIT":
                return ExitAIRecommendation(
                    action=action,
                    confidence=confidence,
                    reason="model_full_exit",
                    baseline_context=sample.baseline_context,
                    raw_probabilities=raw_probabilities,
                )

            return self._noop(
                "model_hold",
                baseline_context=sample.baseline_context,
                raw_probabilities=raw_probabilities,
            )
        except Exception:
            return self._noop("prediction_failed")

    def _noop(
        self,
        reason: str,
        *,
        baseline_context: dict[str, Any] | None = None,
        raw_probabilities: dict[str, float] | None = None,
    ) -> ExitAIRecommendation:
        return ExitAIRecommendation(
            action="HOLD",
            confidence=0.0,
            reason=reason,
            no_op=True,
            baseline_context=baseline_context or {},
            raw_probabilities=raw_probabilities or {},
        )

    @staticmethod
    def _is_monotonic_tightening(
        *,
        direction: str,
        current_stop_loss: float,
        proposed_stop_loss: float | None,
    ) -> bool:
        if proposed_stop_loss is None:
            return False
        if direction == "BUY":
            return float(proposed_stop_loss) > float(current_stop_loss)
        if direction == "SELL":
            return float(proposed_stop_loss) < float(current_stop_loss)
        return False
