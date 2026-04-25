"""Training and comparison pipeline for the autonomy decision head."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ai_engine.calibration.artifacts import (
    write_calibration_artifact,
    write_threshold_artifact,
)
from ai_engine.features.feature_scaler import FeatureScaler
from ai_engine.prediction.decision_head import (
    DECISION_HEAD_NAME,
    FEATURE_MANIFEST_FILENAME,
    MODEL_FILENAME,
    SCALER_FILENAME,
)
from ai_engine.training.model_versioning import (
    cleanup_old_versions,
    create_specialist_version_dir,
    get_specialist_root,
    update_specialist_production_pointer,
    write_version_json,
)
from ai_engine.training.walk_forward import WalkForwardValidator, serialize_window_spec


def train_decision_head(
    dataset_frame: pd.DataFrame,
    *,
    feature_names: list[str],
    saved_models_dir: str = "ai_engine/saved_models",
    label_column: str = "policy_label",
    purge_gap: int = 12,
    keep_versions: int = 5,
) -> dict[str, Any]:
    """Train and persist a versioned autonomy decision-head artifact."""
    if not feature_names:
        raise ValueError("Decision-head feature_names must not be empty")
    if label_column not in dataset_frame.columns:
        raise ValueError(f"Missing label column: {label_column}")

    train_frame, val_frame, test_frame = _chronological_splits(dataset_frame, purge_gap)
    scaler = FeatureScaler()
    scaler.fit(train_frame, feature_names)
    X_train = scaler.transform(train_frame)[feature_names].values.astype(np.float32)
    X_val = scaler.transform(val_frame)[feature_names].values.astype(np.float32)
    X_test = scaler.transform(test_frame)[feature_names].values.astype(np.float32)
    y_train = train_frame[label_column].to_numpy(dtype=int)
    y_val = val_frame[label_column].to_numpy(dtype=int)
    y_test = test_frame[label_column].to_numpy(dtype=int)

    model = _fit_classifier(X_train, y_train, X_val, y_val)
    probabilities = _predict_probabilities(model, X_test)
    metrics = _decision_metrics(y_test, probabilities)

    version_dir = create_specialist_version_dir(saved_models_dir, DECISION_HEAD_NAME)
    root_dir = get_specialist_root(saved_models_dir, DECISION_HEAD_NAME)
    model_path = os.path.join(version_dir, MODEL_FILENAME)
    scaler_path = os.path.join(version_dir, SCALER_FILENAME)
    manifest_path = os.path.join(version_dir, FEATURE_MANIFEST_FILENAME)
    scaler.save(scaler_path)
    joblib.dump({"model": model, "feature_names": feature_names}, model_path)

    manifest = {
        "schema_version": 1,
        "specialist_name": DECISION_HEAD_NAME,
        "feature_names": feature_names,
        "label_column": label_column,
        "action_space": ["SELL", "HOLD", "BUY"],
    }
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2)

    calibration_path = write_calibration_artifact(
        version_dir,
        {
            "models": {
                "decision_head": {
                    "method": "empirical",
                    "validation_metrics": metrics,
                }
            }
        },
    )
    threshold_path = write_threshold_artifact(
        version_dir,
        {
            "thresholds": {
                "default": {
                    "BUY": {"min_confidence": 0.55, "min_margin": 0.05},
                    "SELL": {"min_confidence": 0.55, "min_margin": 0.05},
                    "HOLD": {"min_confidence": 0.40, "min_margin": 0.0},
                }
            }
        },
    )
    metadata = {
        "schema_version": 1,
        "artifact_type": "decision_head",
        "training_date": datetime.now(timezone.utc).isoformat(),
        "feature_names": feature_names,
        "metrics": metrics,
        "purge_gap": int(purge_gap),
        "calibration_artifact": os.path.basename(calibration_path),
        "threshold_artifact": os.path.basename(threshold_path),
    }
    version_json = write_version_json(version_dir, metadata)
    shutil.copy2(version_json, os.path.join(version_dir, "decision_head_version.json"))
    update_specialist_production_pointer(
        saved_models_dir,
        DECISION_HEAD_NAME,
        version_dir,
        artifact_files=[
            MODEL_FILENAME,
            SCALER_FILENAME,
            FEATURE_MANIFEST_FILENAME,
            "calibration.json",
            "thresholds.json",
            "decision_head_version.json",
            "version.json",
        ],
    )
    cleanup_old_versions(root_dir, keep=keep_versions)
    return {
        "version_dir": version_dir,
        "root_dir": root_dir,
        "feature_names": feature_names,
        "metrics": metrics,
        "manifest": manifest,
    }


def compare_decision_head_to_champion(
    dataset_frame: pd.DataFrame,
    *,
    feature_names: list[str],
    purge_gap: int = 12,
    min_train_samples: int = 120,
    min_test_samples: int = 40,
) -> dict[str, Any]:
    """Run an identical-window champion-vs-decision-head comparison."""
    validator = WalkForwardValidator(
        purge_gap=purge_gap,
        min_train_samples=min_train_samples,
        min_test_samples=min_test_samples,
    )
    windows = validator.calculate_windows(len(dataset_frame))
    if not windows:
        raise ValueError("No valid walk-forward windows for decision-head comparison")

    reports: list[dict[str, Any]] = []
    champion_metrics: list[dict[str, float]] = []
    candidate_metrics: list[dict[str, float]] = []
    for window in windows:
        result = _run_window(dataset_frame, feature_names, window)
        champion_metrics.append(result["champion"])
        candidate_metrics.append(result["candidate"])
        entry = serialize_window_spec(window, purge_gap=purge_gap)
        entry["scaler_scope"] = "train_only"
        entry.update(result)
        reports.append(entry)

    champion = _aggregate_metrics(champion_metrics)
    candidate = _aggregate_metrics(candidate_metrics)
    return {
        "schema_version": 1,
        "purge_gap": int(purge_gap),
        "window_count": len(reports),
        "comparison": {
            "champion": champion,
            "decision_head_candidate": candidate,
        },
        "deltas": {
            "profit_factor_delta": round(candidate["profit_factor"] - champion["profit_factor"], 6),
            "drawdown_delta": round(champion["max_drawdown_pct"] - candidate["max_drawdown_pct"], 6),
            "calibration_delta": round(candidate["calibration_score"] - champion["calibration_score"], 6),
            "trade_count_retention": round(candidate["trade_count"] / max(champion["trade_count"], 1), 6),
        },
        "disagreement_buckets": _disagreement_buckets(dataset_frame),
        "windows": reports,
    }


def evaluate_decision_head_candidate(
    champion_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
    *,
    max_hold_rate: float = 0.80,
    min_profit_factor_delta: float = 0.0,
    min_calibration_score: float = 0.45,
) -> dict[str, Any]:
    """Promotion gate for the decision-head candidate."""
    reasons: list[str] = []
    if candidate_metrics.get("hold_rate", 1.0) > max_hold_rate:
        reasons.append("candidate is HOLD-dominant")
    if candidate_metrics.get("profit_factor", 0.0) < champion_metrics.get("profit_factor", 0.0) + min_profit_factor_delta:
        reasons.append("profit factor is below champion requirement")
    if candidate_metrics.get("calibration_score", 0.0) < min_calibration_score:
        reasons.append("calibration score is below threshold")
    return {
        "promote": not reasons,
        "reasons": reasons,
        "champion": champion_metrics,
        "candidate": candidate_metrics,
    }


def _chronological_splits(frame: pd.DataFrame, purge_gap: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    n = len(frame)
    train_end = int(n * 0.70)
    val_start = min(train_end + purge_gap, n)
    val_end = int(n * 0.85)
    test_start = min(val_end + purge_gap, n)
    if test_start >= n:
        val_start = train_end
        test_start = val_end
    return (
        frame.iloc[:train_end].copy(),
        frame.iloc[val_start:val_end].copy(),
        frame.iloc[test_start:].copy(),
    )


def _fit_classifier(X_train: np.ndarray, y_train: np.ndarray, X_val: np.ndarray, y_val: np.ndarray) -> Any:
    if len(np.unique(y_train)) < 2:
        raise ValueError("Decision-head training needs at least two classes")
    try:
        from sklearn.linear_model import LogisticRegression

        model = LogisticRegression(max_iter=500, multi_class="auto", random_state=42)
        model.fit(X_train, y_train)
        return model
    except Exception:
        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier(n_estimators=80, max_depth=6, random_state=42)
        model.fit(X_train, y_train)
        return model


def _predict_probabilities(model: Any, X: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(X), dtype=float)
    if probabilities.shape[1] != 3:
        classes = list(getattr(model, "classes_", range(probabilities.shape[1])))
        padded = np.zeros((len(X), 3), dtype=float)
        for idx, label in enumerate(classes):
            if int(label) in (0, 1, 2):
                padded[:, int(label)] = probabilities[:, idx]
        probabilities = padded
    return probabilities


def _decision_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float]:
    predicted = np.argmax(probabilities, axis=1)
    confidence = probabilities.max(axis=1)
    correct = (predicted == y_true).astype(float)
    non_hold = predicted != 1
    wins = float(np.sum((predicted == y_true) & non_hold))
    losses = float(np.sum((predicted != y_true) & non_hold))
    profit_factor = wins / max(losses, 1.0)
    return {
        "accuracy": round(float(np.mean(correct)), 6),
        "calibration_score": round(1.0 - float(np.mean(np.abs(confidence - correct))), 6),
        "profit_factor": round(float(profit_factor), 6),
        "max_drawdown_pct": round(float(losses / max(len(y_true), 1)), 6),
        "trade_count": int(np.sum(non_hold)),
        "hold_rate": round(float(np.mean(predicted == 1)), 6),
        "confidence_mean": round(float(np.mean(confidence)), 6),
    }


def _run_window(frame: pd.DataFrame, feature_names: list[str], window: Any) -> dict[str, Any]:
    train = frame.iloc[window.train_start:window.train_end].copy()
    test = frame.iloc[window.test_start:window.test_end].copy()
    val_size = max(8, int(len(train) * 0.15))
    fit = train.iloc[:-val_size].copy()
    val = train.iloc[-val_size:].copy()
    scaler = FeatureScaler()
    scaler.fit(fit, feature_names)
    X_fit = scaler.transform(fit)[feature_names].values.astype(np.float32)
    X_val = scaler.transform(val)[feature_names].values.astype(np.float32)
    X_test = scaler.transform(test)[feature_names].values.astype(np.float32)
    y_fit = fit["policy_label"].to_numpy(dtype=int)
    y_val = val["policy_label"].to_numpy(dtype=int)
    y_test = test["policy_label"].to_numpy(dtype=int)
    model = _fit_classifier(X_fit, y_fit, X_val, y_val)
    candidate_probs = _predict_probabilities(model, X_test)
    champion_labels = test["preliminary_label"].to_numpy(dtype=int)
    champion_probs = np.zeros((len(test), 3), dtype=float)
    champion_probs[np.arange(len(test)), champion_labels] = 1.0
    return {
        "champion": _decision_metrics(y_test, champion_probs),
        "candidate": _decision_metrics(y_test, candidate_probs),
    }


def _aggregate_metrics(metrics: list[dict[str, float]]) -> dict[str, float]:
    keys = ("accuracy", "calibration_score", "profit_factor", "max_drawdown_pct", "hold_rate", "confidence_mean")
    aggregated = {key: round(float(np.mean([item[key] for item in metrics])), 6) for key in keys}
    aggregated["trade_count"] = int(sum(int(item["trade_count"]) for item in metrics))
    return aggregated


def _disagreement_buckets(frame: pd.DataFrame) -> dict[str, Any]:
    disagreement = frame[frame["preliminary_action"] != frame["policy_action"]]
    return {
        "total_disagreements": int(len(disagreement)),
        "blocked_disagreements": int(disagreement.get("blocked", pd.Series(dtype=bool)).sum()),
        "disagreement_rate": round(len(disagreement) / max(len(frame), 1), 6),
    }
