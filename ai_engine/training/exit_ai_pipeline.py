"""Training and walk-forward comparison helpers for Exit-AI specialists."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
import pandas as pd

from ..features.feature_scaler import FeatureScaler
from .data_preparation import DataPreparation
from .exit_ai_labels import (
    ACTION_TO_LABEL,
    EXIT_AI_ACTIONS,
    LABEL_TO_ACTION,
    build_exit_training_samples,
)
from .model_versioning import (
    cleanup_old_versions,
    create_specialist_version_dir,
    get_specialist_root,
    update_specialist_production_pointer,
    write_version_json,
)
from .walk_forward import WalkForwardValidator, serialize_window_spec

DEFAULT_EXIT_AI_NAME = "exit_ai"
MODEL_FILENAME = "exit_ai_lightgbm.pkl"
SCALER_FILENAME = "exit_ai_scaler.pkl"
FEATURE_BLOCK_FILENAME = "feature_block.json"
ACTION_MANIFEST_FILENAME = "action_manifest.json"
VERSION_ALIAS_FILENAME = "exit_ai_version.json"
TRAINING_REPORT_FILENAME = "exit_ai_training_report.json"


@dataclass
class ExitAIBundle:
    specialist_name: str
    version_dir: str
    root_dir: str
    feature_names: list[str]
    action_manifest: dict[str, Any]
    metadata: dict[str, Any]
    model: Any
    scaler: FeatureScaler


def train_exit_ai_specialist(
    df: pd.DataFrame,
    *,
    saved_models_dir: str = "ai_engine/saved_models",
    specialist_name: str = DEFAULT_EXIT_AI_NAME,
    purge_gap: int = 12,
    keep_versions: int = 5,
) -> dict[str, Any]:
    """Train and persist the isolated Exit-AI specialist artifacts."""
    dataset = build_exit_training_samples(df)
    feature_names = dataset["feature_names"]
    frame = dataset["frame"].copy()
    data_prep = DataPreparation()
    X, y = data_prep.prepare_features_labels(
        frame[feature_names + ["action_label"]].copy(),
        feature_names,
        "action_label",
    )
    splits = data_prep.split_chronological(X, y, purge_gap=purge_gap)
    X_train, y_train = splits["train"]
    X_val, y_val = splits["val"]
    X_test, y_test = splits["test"]

    if len(X_train) < 24 or len(X_val) < 8 or len(X_test) < 8:
        raise ValueError("Insufficient split sizes for Exit-AI training")

    scaler = FeatureScaler()
    train_df = pd.DataFrame(X_train, columns=feature_names)
    val_df = pd.DataFrame(X_val, columns=feature_names)
    test_df = pd.DataFrame(X_test, columns=feature_names)
    scaler.fit(train_df, feature_names)
    X_train_scaled = scaler.transform(train_df)[feature_names].values.astype(np.float32)
    X_val_scaled = scaler.transform(val_df)[feature_names].values.astype(np.float32)
    X_test_scaled = scaler.transform(test_df)[feature_names].values.astype(np.float32)

    model = _fit_exit_ai_classifier(X_train_scaled, y_train, X_val_scaled, y_val)
    probabilities = _predict_probabilities(model, X_test_scaled)
    predictions = np.argmax(probabilities, axis=1)
    metrics = _classification_metrics(y_test, predictions, probabilities)

    version_dir = create_specialist_version_dir(saved_models_dir, specialist_name)
    specialist_root = get_specialist_root(saved_models_dir, specialist_name)
    model_path = os.path.join(version_dir, MODEL_FILENAME)
    scaler_path = os.path.join(version_dir, SCALER_FILENAME)
    feature_block_path = os.path.join(version_dir, FEATURE_BLOCK_FILENAME)
    action_manifest_path = os.path.join(version_dir, ACTION_MANIFEST_FILENAME)
    report_path = os.path.join(version_dir, TRAINING_REPORT_FILENAME)

    scaler.save(scaler_path)
    joblib.dump(
        {
            "model": model,
            "feature_names": feature_names,
            "action_map": dict(ACTION_TO_LABEL),
            "model_type": type(model).__name__,
        },
        model_path,
    )

    feature_block = {
        "schema_version": 1,
        "specialist_name": specialist_name,
        "feature_names": feature_names,
        "label_column": "action_label",
    }
    with open(feature_block_path, "w", encoding="utf-8") as handle:
        json.dump(feature_block, handle, indent=2)
    with open(action_manifest_path, "w", encoding="utf-8") as handle:
        json.dump(dataset["action_manifest"], handle, indent=2)

    report = {
        "schema_version": 1,
        "specialist_name": specialist_name,
        "metrics": metrics,
        "class_balance": dataset["class_balance"],
        "split_sizes": {
            "train": int(len(X_train)),
            "val": int(len(X_val)),
            "test": int(len(X_test)),
        },
    }
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    metadata = {
        "schema_version": 1,
        "artifact_type": "exit_ai_specialist",
        "specialist_name": specialist_name,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "version_dir": os.path.basename(version_dir),
        "feature_names": feature_names,
        "action_manifest": os.path.basename(action_manifest_path),
        "feature_block": os.path.basename(feature_block_path),
        "training_report": os.path.basename(report_path),
        "class_balance": dataset["class_balance"],
        "metrics": metrics,
        "purge_gap": int(purge_gap),
    }
    version_json_path = write_version_json(version_dir, metadata)
    shutil.copy2(version_json_path, os.path.join(version_dir, VERSION_ALIAS_FILENAME))

    update_specialist_production_pointer(
        saved_models_dir,
        specialist_name,
        version_dir,
        artifact_files=[
            MODEL_FILENAME,
            SCALER_FILENAME,
            FEATURE_BLOCK_FILENAME,
            ACTION_MANIFEST_FILENAME,
            VERSION_ALIAS_FILENAME,
            TRAINING_REPORT_FILENAME,
            "version.json",
        ],
    )
    cleanup_old_versions(specialist_root, keep=keep_versions)

    return {
        "specialist_name": specialist_name,
        "specialist_root": specialist_root,
        "version_dir": version_dir,
        "feature_names": feature_names,
        "action_manifest": dataset["action_manifest"],
        "metadata": metadata,
        "metrics": metrics,
        "report_path": report_path,
    }


def load_exit_ai_bundle(
    saved_models_dir: str = "ai_engine/saved_models",
    *,
    specialist_name: str = DEFAULT_EXIT_AI_NAME,
    expected_features: list[str] | None = None,
) -> ExitAIBundle:
    """Load the promoted Exit-AI bundle from its isolated specialist root."""
    root_dir = get_specialist_root(saved_models_dir, specialist_name)
    pointer_path = os.path.join(root_dir, "production.json")
    if not os.path.exists(pointer_path):
        raise FileNotFoundError(
            f"Exit-AI production pointer not found: {pointer_path}"
        )

    with open(pointer_path, "r", encoding="utf-8") as handle:
        pointer = json.load(handle)
    version_dir = str(
        pointer.get("path")
        or os.path.join(root_dir, str(pointer.get("version_dir", "")))
    )

    feature_block_path = os.path.join(version_dir, FEATURE_BLOCK_FILENAME)
    action_manifest_path = os.path.join(version_dir, ACTION_MANIFEST_FILENAME)
    version_path = os.path.join(version_dir, VERSION_ALIAS_FILENAME)
    if not os.path.exists(version_path):
        version_path = os.path.join(version_dir, "version.json")

    with open(feature_block_path, "r", encoding="utf-8") as handle:
        feature_block = json.load(handle)
    with open(action_manifest_path, "r", encoding="utf-8") as handle:
        action_manifest = json.load(handle)
    with open(version_path, "r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    feature_names = list(feature_block.get("feature_names", []))
    if expected_features is not None and list(expected_features) != feature_names:
        raise ValueError(
            "Feature block mismatch between expected features and Exit-AI artifacts"
        )

    scaler = FeatureScaler()
    scaler.load(os.path.join(version_dir, SCALER_FILENAME))
    model_payload = joblib.load(os.path.join(version_dir, MODEL_FILENAME))
    model = model_payload["model"]

    scaler_features = scaler.get_feature_names()
    if scaler_features and scaler_features != feature_names:
        raise ValueError("Feature block mismatch between scaler and feature block")

    return ExitAIBundle(
        specialist_name=specialist_name,
        version_dir=version_dir,
        root_dir=root_dir,
        feature_names=feature_names,
        action_manifest=action_manifest,
        metadata=metadata,
        model=model,
        scaler=scaler,
    )


def compare_exit_ai_to_baseline(
    df: pd.DataFrame,
    *,
    purge_gap: int = 12,
    min_train_samples: int = 120,
    min_test_samples: int = 40,
    specialist_name: str = DEFAULT_EXIT_AI_NAME,
) -> dict[str, Any]:
    """Compare deterministic baseline actions to the trained Exit-AI candidate."""
    dataset = build_exit_training_samples(df)
    feature_names = dataset["feature_names"]
    frame = dataset["frame"].copy()

    validator = WalkForwardValidator(
        purge_gap=purge_gap,
        min_train_samples=min_train_samples,
        min_test_samples=min_test_samples,
    )
    windows = validator.calculate_windows(len(frame))
    if not windows:
        raise ValueError("No valid walk-forward windows for Exit-AI comparison")

    baseline_metrics: list[dict[str, Any]] = []
    candidate_metrics: list[dict[str, Any]] = []
    window_reports: list[dict[str, Any]] = []

    for window in windows:
        fit_result = _run_exit_ai_window(
            frame=frame,
            feature_names=feature_names,
            window=window,
        )
        baseline_metrics.append(fit_result["baseline"])
        candidate_metrics.append(fit_result["candidate"])

        window_report = serialize_window_spec(window, purge_gap=purge_gap)
        window_report["scaler_scope"] = "train_only"
        window_report["baseline"] = fit_result["baseline"]
        window_report["exit_ai_candidate"] = fit_result["candidate"]
        window_report["delta"] = _build_delta_metrics(
            fit_result["baseline"],
            fit_result["candidate"],
        )
        window_reports.append(window_report)

    baseline_summary = _aggregate_policy_metrics(baseline_metrics)
    candidate_summary = _aggregate_policy_metrics(candidate_metrics)

    return {
        "schema_version": 1,
        "specialist_name": specialist_name,
        "purge_gap": int(purge_gap),
        "window_count": len(window_reports),
        "feature_block": feature_names,
        "action_manifest": dataset["action_manifest"],
        "comparison": {
            "baseline": baseline_summary,
            "exit_ai_candidate": candidate_summary,
        },
        "deltas": _build_delta_metrics(baseline_summary, candidate_summary),
        "windows": window_reports,
    }


def _fit_exit_ai_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
) -> Any:
    unique_classes = np.unique(y_train)
    if len(unique_classes) < 2:
        raise ValueError("Exit-AI training needs at least two action classes")

    try:
        import lightgbm as lgb

        model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=len(EXIT_AI_ACTIONS),
            n_estimators=90,
            learning_rate=0.07,
            max_depth=6,
            subsample=0.9,
            colsample_bytree=0.9,
            min_child_samples=12,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        )
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[
                lgb.early_stopping(stopping_rounds=20, verbose=False),
                lgb.log_evaluation(period=0),
            ],
        )
        return model
    except ImportError:
        from sklearn.ensemble import RandomForestClassifier

        model = RandomForestClassifier(
            n_estimators=80,
            max_depth=6,
            random_state=42,
        )
        model.fit(X_train, y_train)
        return model


def _predict_probabilities(model: Any, X: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(model.predict_proba(X), dtype=float)
    if probabilities.ndim != 2:
        raise ValueError("Model did not return a 2D probability matrix")
    if probabilities.shape[1] != len(EXIT_AI_ACTIONS):
        padded = np.zeros((len(X), len(EXIT_AI_ACTIONS)), dtype=float)
        padded[:, : probabilities.shape[1]] = probabilities
        probabilities = padded
    return probabilities


def _classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, float]:
    confidence = probabilities.max(axis=1)
    correct = (y_true == y_pred).astype(float)
    calibration_score = 1.0 - float(np.mean(np.abs(confidence - correct)))
    return {
        "accuracy": round(float(np.mean(correct)), 6),
        "calibration_score": round(float(calibration_score), 6),
        "confidence_mean": round(float(np.mean(confidence)), 6),
        "non_hold_rate": round(float(np.mean(y_pred != ACTION_TO_LABEL["HOLD"])), 6),
        "hold_rate": round(float(np.mean(y_pred == ACTION_TO_LABEL["HOLD"])), 6),
    }


def _run_exit_ai_window(
    *,
    frame: pd.DataFrame,
    feature_names: list[str],
    window: Any,
) -> dict[str, Any]:
    train_frame = frame.iloc[window.train_start : window.train_end].copy()
    test_frame = frame.iloc[window.test_start : window.test_end].copy()
    if len(train_frame) < 24 or len(test_frame) < 8:
        raise ValueError("Window too small for Exit-AI comparison")

    val_size = max(8, int(len(train_frame) * 0.15))
    fit_frame = train_frame.iloc[:-val_size].copy()
    val_frame = train_frame.iloc[-val_size:].copy()

    scaler = FeatureScaler()
    scaler.fit(fit_frame, feature_names)
    X_fit = scaler.transform(fit_frame)[feature_names].values.astype(np.float32)
    X_val = scaler.transform(val_frame)[feature_names].values.astype(np.float32)
    X_test = scaler.transform(test_frame)[feature_names].values.astype(np.float32)

    y_fit = fit_frame["action_label"].to_numpy(dtype=int)
    y_val = val_frame["action_label"].to_numpy(dtype=int)
    y_test = test_frame["action_label"].to_numpy(dtype=int)

    model = _fit_exit_ai_classifier(X_fit, y_fit, X_val, y_val)
    probabilities = _predict_probabilities(model, X_test)
    predictions = np.argmax(probabilities, axis=1)
    predicted_actions = [LABEL_TO_ACTION[int(label)] for label in predictions]
    baseline_actions = test_frame["action"].astype(str).tolist()

    baseline_metrics = _evaluate_exit_policy(
        frame=test_frame,
        actions=baseline_actions,
        confidences=np.ones(len(test_frame), dtype=float),
        true_labels=y_test,
    )
    candidate_metrics = _evaluate_exit_policy(
        frame=test_frame,
        actions=predicted_actions,
        confidences=probabilities.max(axis=1),
        true_labels=y_test,
    )
    return {
        "baseline": baseline_metrics,
        "candidate": candidate_metrics,
    }


def _evaluate_exit_policy(
    *,
    frame: pd.DataFrame,
    actions: list[str],
    confidences: np.ndarray,
    true_labels: np.ndarray,
) -> dict[str, Any]:
    protection = 0.0
    retained_upside = 0.0
    early_exit_cost = 0.0
    residual_drawdown = 0.0
    trade_retention = 0.0
    action_counts = {action: 0 for action in EXIT_AI_ACTIONS}

    for row, action, confidence, true_label in zip(
        frame.itertuples(index=False),
        actions,
        confidences,
        true_labels,
        strict=True,
    ):
        action = str(action)
        action_counts[action] += 1
        adverse_r = max(float(getattr(row, "future_adverse_r", 0.0)), 0.0)
        favorable_r = max(float(getattr(row, "future_favorable_r", 0.0)), 0.0)
        close_fraction = max(
            float(getattr(row, "baseline_partial_close_fraction", 0.5)),
            0.5,
        )
        stop_buffer_r = max(float(getattr(row, "current_stop_buffer_r", 0.0)), 0.0)

        if action == "HOLD":
            action_protection = 0.0
            action_retained = favorable_r
            action_cost = 0.0
            retention = 1.0
        elif action == "TIGHTEN_SL":
            action_protection = min(adverse_r, max(stop_buffer_r * 0.5, 0.25))
            action_retained = max(favorable_r - 0.10, 0.0)
            action_cost = max(favorable_r - action_retained, 0.0)
            retention = 1.0
        elif action == "PARTIAL_CLOSE":
            action_protection = adverse_r * close_fraction
            action_retained = favorable_r * (1.0 - close_fraction)
            action_cost = favorable_r * close_fraction
            retention = 1.0 - close_fraction
        else:
            action_protection = adverse_r
            action_retained = 0.0
            action_cost = favorable_r
            retention = 0.0

        protection += action_protection
        retained_upside += action_retained
        early_exit_cost += action_cost
        residual_drawdown += max(adverse_r - action_protection, 0.0)
        trade_retention += retention

    total = max(len(actions), 1)
    confidence_arr = np.asarray(confidences, dtype=float)
    correct = np.asarray(
        [ACTION_TO_LABEL[action] == int(label) for action, label in zip(actions, true_labels, strict=True)],
        dtype=float,
    )
    calibration_score = 1.0 - float(np.mean(np.abs(confidence_arr - correct)))

    profit_factor_proxy = (
        (protection + retained_upside)
        / max(early_exit_cost + residual_drawdown, 1e-6)
    )
    return {
        "drawdown_contained": round(float(protection), 6),
        "upside_retained": round(float(retained_upside), 6),
        "early_exit_cost": round(float(early_exit_cost), 6),
        "residual_drawdown_total": round(float(residual_drawdown), 6),
        "max_drawdown_proxy": round(float(residual_drawdown / total), 6),
        "trade_retention": round(float(trade_retention / total), 6),
        "accuracy": round(float(np.mean(correct)), 6),
        "calibration_score": round(float(calibration_score), 6),
        "confidence_mean": round(float(np.mean(confidence_arr)), 6),
        "hold_rate": round(float(action_counts["HOLD"] / total), 6),
        "non_hold_rate": round(
            float((total - action_counts["HOLD"]) / total),
            6,
        ),
        "profit_factor_proxy": round(float(profit_factor_proxy), 6),
        "action_counts": action_counts,
    }


def _aggregate_policy_metrics(metrics_list: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics_list:
        return {
            "drawdown_contained": 0.0,
            "upside_retained": 0.0,
            "early_exit_cost": 0.0,
            "residual_drawdown_total": 0.0,
            "max_drawdown_proxy": 0.0,
            "trade_retention": 0.0,
            "accuracy": 0.0,
            "calibration_score": 0.0,
            "confidence_mean": 0.0,
            "hold_rate": 1.0,
            "non_hold_rate": 0.0,
            "profit_factor_proxy": 0.0,
            "action_counts": {action: 0 for action in EXIT_AI_ACTIONS},
        }

    summed = {
        "drawdown_contained": sum(item["drawdown_contained"] for item in metrics_list),
        "upside_retained": sum(item["upside_retained"] for item in metrics_list),
        "early_exit_cost": sum(item["early_exit_cost"] for item in metrics_list),
        "residual_drawdown_total": sum(
            item["residual_drawdown_total"] for item in metrics_list
        ),
    }
    averaged_keys = (
        "max_drawdown_proxy",
        "trade_retention",
        "accuracy",
        "calibration_score",
        "confidence_mean",
        "hold_rate",
        "non_hold_rate",
    )
    aggregated = {
        key: round(
            float(np.mean([item[key] for item in metrics_list])),
            6,
        )
        for key in averaged_keys
    }
    counts = {action: 0 for action in EXIT_AI_ACTIONS}
    for item in metrics_list:
        for action, count in item["action_counts"].items():
            counts[action] += int(count)
    aggregated.update({key: round(value, 6) for key, value in summed.items()})
    aggregated["action_counts"] = counts
    aggregated["profit_factor_proxy"] = round(
        (aggregated["drawdown_contained"] + aggregated["upside_retained"])
        / max(
            aggregated["early_exit_cost"] + aggregated["residual_drawdown_total"],
            1e-6,
        ),
        6,
    )
    return aggregated


def _build_delta_metrics(
    baseline_metrics: dict[str, Any],
    candidate_metrics: dict[str, Any],
) -> dict[str, float]:
    return {
        "profit_factor_delta": round(
            float(
                candidate_metrics.get("profit_factor_proxy", 0.0)
                - baseline_metrics.get("profit_factor_proxy", 0.0)
            ),
            6,
        ),
        "drawdown_delta": round(
            float(
                baseline_metrics.get("max_drawdown_proxy", 0.0)
                - candidate_metrics.get("max_drawdown_proxy", 0.0)
            ),
            6,
        ),
        "calibration_delta": round(
            float(
                candidate_metrics.get("calibration_score", 0.0)
                - baseline_metrics.get("calibration_score", 0.0)
            ),
            6,
        ),
        "trade_retention_delta": round(
            float(
                candidate_metrics.get("trade_retention", 0.0)
                - baseline_metrics.get("trade_retention", 0.0)
            ),
            6,
        ),
        "protection_delta": round(
            float(
                candidate_metrics.get("drawdown_contained", 0.0)
                - baseline_metrics.get("drawdown_contained", 0.0)
            ),
            6,
        ),
        "retained_upside_delta": round(
            float(
                candidate_metrics.get("upside_retained", 0.0)
                - baseline_metrics.get("upside_retained", 0.0)
            ),
            6,
        ),
    }
