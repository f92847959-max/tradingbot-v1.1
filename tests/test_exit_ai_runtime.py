"""Tests for bounded Exit-AI runtime recommendations."""

from __future__ import annotations

import numpy as np

from ai_engine.prediction.exit_ai_advisor import ExitAIAdvisor
from ai_engine.training.exit_ai_pipeline import train_exit_ai_specialist
from tests._exit_ai_fixtures import make_exit_ai_frame


class _IdentityScaler:
    def transform(self, frame):
        return frame


class _FixedModel:
    def __init__(self, probabilities):
        self._probabilities = np.asarray([probabilities], dtype=float)

    def predict_proba(self, _X):
        return self._probabilities


def test_exit_ai_advisor_falls_back_to_noop_when_disabled() -> None:
    advisor = ExitAIAdvisor(enabled=False)
    recommendation = advisor.recommend(make_exit_ai_frame(rows=1).iloc[0].to_dict())
    assert recommendation.no_op is True
    assert recommendation.reason == "advisor_disabled"


def test_exit_ai_advisor_falls_back_to_noop_when_artifacts_missing(tmp_path) -> None:
    advisor = ExitAIAdvisor(saved_models_dir=str(tmp_path), enabled=True)
    recommendation = advisor.recommend(make_exit_ai_frame(rows=1).iloc[0].to_dict())
    assert recommendation.no_op is True
    assert recommendation.reason == "artifacts_unavailable"


def test_exit_ai_advisor_recommendation_is_bounded_to_allowed_actions(tmp_path) -> None:
    saved_models_dir = tmp_path / "saved_models"
    train_exit_ai_specialist(
        make_exit_ai_frame(),
        saved_models_dir=str(saved_models_dir),
    )
    advisor = ExitAIAdvisor(saved_models_dir=str(saved_models_dir), enabled=True)
    recommendation = advisor.recommend(make_exit_ai_frame(rows=1).iloc[0].to_dict())

    assert recommendation.action in {
        "HOLD",
        "TIGHTEN_SL",
        "PARTIAL_CLOSE",
        "FULL_EXIT",
    }


def test_exit_ai_advisor_rejects_risk_widening_stop_proposal(monkeypatch) -> None:
    advisor = ExitAIAdvisor(enabled=True)
    advisor._bundle = type(
        "Bundle",
        (),
        {
            "feature_names": ["x"],
            "scaler": _IdentityScaler(),
            "model": _FixedModel([0.0, 1.0, 0.0, 0.0]),
        },
    )()
    monkeypatch.setattr(
        "ai_engine.prediction.exit_ai_advisor.ExitSnapshotBuilder.build_snapshot",
        lambda _self, _snapshot: type(
            "Sample",
            (),
            {
                "features": {"x": 1.0},
                "baseline_context": {
                    "baseline_trailing_sl": 1998.0,
                    "baseline_trailing_reason": "atr_trail",
                },
            },
        )(),
    )

    recommendation = advisor.recommend(
        {
            "direction": "BUY",
            "current_stop_loss": 2000.0,
        }
    )

    assert recommendation.no_op is True
    assert recommendation.reason == "risk_widening_rejected"
