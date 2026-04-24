"""Specialist training and comparison helpers for Phase 12.3."""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ..features.feature_engineer import FeatureEngineer
from ..features.feature_scaler import FeatureScaler
from ..models.lightgbm_model import LightGBMModel
from .data_preparation import DataPreparation
from .label_generator import LabelGenerator
from .model_versioning import (
    cleanup_old_versions,
    create_specialist_version_dir,
    get_specialist_root,
    update_specialist_production_pointer,
    write_version_json,
)
from .walk_forward import WalkForwardValidator, serialize_window_spec

logger = logging.getLogger(__name__)

DEFAULT_SPECIALIST_NAME = "market_structure_liquidity"
DEFAULT_LABEL_COLUMN = "label"


@dataclass
class SpecialistBundle:
    specialist_name: str
    version_dir: str
    root_dir: str
    feature_names: list[str]
    model: LightGBMModel
    scaler: FeatureScaler
    metadata: dict[str, Any]
    feature_block: dict[str, Any]


def train_specialist_model(
    df: pd.DataFrame,
    *,
    saved_models_dir: str = "ai_engine/saved_models",
    specialist_name: str = DEFAULT_SPECIALIST_NAME,
    timeframe: str = "5m",
    label_column: str = DEFAULT_LABEL_COLUMN,
    purge_gap: int | None = None,
    keep_versions: int = 5,
) -> dict[str, Any]:
    """Train and persist the isolated specialist model artifacts."""
    prepared = _prepare_feature_sets(
        df,
        timeframe=timeframe,
        label_column=label_column,
    )
    specialist_frame = prepared["specialist_frame"]
    specialist_features = prepared["specialist_features"]

    if specialist_frame.empty:
        raise ValueError("Specialist frame is empty after warmup removal")

    resolved_purge_gap = _resolve_purge_gap(purge_gap, prepared["label_horizon"])
    split_artifacts = _train_eval_split(
        specialist_frame,
        specialist_features,
        label_column=label_column,
        purge_gap=resolved_purge_gap,
    )

    specialist_root = get_specialist_root(saved_models_dir, specialist_name)
    version_dir = create_specialist_version_dir(saved_models_dir, specialist_name)

    model_path = os.path.join(version_dir, "specialist_lightgbm.pkl")
    scaler_path = os.path.join(version_dir, "specialist_scaler.pkl")
    feature_block_path = os.path.join(version_dir, "feature_block.json")
    specialist_version_path = os.path.join(version_dir, "specialist_version.json")

    split_artifacts["model"].save(model_path)
    split_artifacts["scaler"].save(scaler_path)

    feature_block = {
        "schema_version": 1,
        "specialist_name": specialist_name,
        "timeframe": timeframe,
        "feature_names": specialist_features,
        "label_column": label_column,
    }
    with open(feature_block_path, "w", encoding="utf-8") as f:
        json.dump(feature_block, f, indent=2, ensure_ascii=False)

    metadata = {
        "schema_version": 1,
        "artifact_type": "specialist_model",
        "specialist_name": specialist_name,
        "training_date": datetime.now(timezone.utc).isoformat(),
        "timeframe": timeframe,
        "version_dir": os.path.basename(version_dir),
        "feature_names": specialist_features,
        "feature_block": os.path.basename(feature_block_path),
        "label_source": prepared["label_source"],
        "purge_gap": resolved_purge_gap,
        "warmup_candles": prepared["warmup_candles"],
        "n_features": len(specialist_features),
        "n_samples_total": int(len(specialist_frame)),
        "split_sizes": split_artifacts["split_sizes"],
        "metrics": split_artifacts["metrics"],
    }
    version_json_path = write_version_json(version_dir, metadata)
    shutil.copy2(version_json_path, specialist_version_path)

    update_specialist_production_pointer(
        saved_models_dir,
        specialist_name,
        version_dir,
        artifact_files=[
            "specialist_lightgbm.pkl",
            "specialist_scaler.pkl",
            "specialist_version.json",
            "feature_block.json",
            "version.json",
        ],
    )
    cleanup_old_versions(specialist_root, keep=keep_versions)

    return {
        "specialist_name": specialist_name,
        "specialist_root": specialist_root,
        "version_dir": version_dir,
        "feature_names": specialist_features,
        "feature_block": feature_block,
        "metadata": metadata,
        "metrics": split_artifacts["metrics"],
    }


def load_specialist_bundle(
    saved_models_dir: str = "ai_engine/saved_models",
    *,
    specialist_name: str = DEFAULT_SPECIALIST_NAME,
    expected_features: list[str] | None = None,
) -> SpecialistBundle:
    """Load the promoted specialist artifacts from the isolated root."""
    root_dir = get_specialist_root(saved_models_dir, specialist_name)
    pointer_path = os.path.join(root_dir, "production.json")
    if not os.path.exists(pointer_path):
        raise FileNotFoundError(
            f"Specialist production pointer not found: {pointer_path}"
        )

    with open(pointer_path, "r", encoding="utf-8") as f:
        pointer = json.load(f)

    version_dir = str(pointer.get("path") or os.path.join(
        root_dir,
        str(pointer.get("version_dir", "")),
    ))
    feature_block_path = os.path.join(version_dir, "feature_block.json")
    version_json_path = os.path.join(version_dir, "specialist_version.json")
    if not os.path.exists(version_json_path):
        version_json_path = os.path.join(version_dir, "version.json")

    if not os.path.exists(feature_block_path):
        raise FileNotFoundError(
            f"Specialist feature block not found: {feature_block_path}"
        )
    if not os.path.exists(version_json_path):
        raise FileNotFoundError(
            f"Specialist metadata not found: {version_json_path}"
        )

    with open(feature_block_path, "r", encoding="utf-8") as f:
        feature_block = json.load(f)
    with open(version_json_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    feature_names = list(feature_block.get("feature_names", []))
    if not feature_names:
        raise ValueError("Specialist feature block is empty")
    if expected_features is not None and list(expected_features) != feature_names:
        raise ValueError(
            "Feature block mismatch between expected features and specialist artifacts"
        )

    scaler = FeatureScaler()
    scaler.load(os.path.join(version_dir, "specialist_scaler.pkl"))
    model = LightGBMModel()
    model.load(os.path.join(version_dir, "specialist_lightgbm.pkl"))

    scaler_features = scaler.get_feature_names()
    model_features = model.get_feature_names()
    if scaler_features and scaler_features != feature_names:
        raise ValueError("Feature block mismatch between scaler and feature block")
    if model_features and model_features != feature_names:
        raise ValueError("Feature block mismatch between model and feature block")

    return SpecialistBundle(
        specialist_name=specialist_name,
        version_dir=version_dir,
        root_dir=root_dir,
        feature_names=feature_names,
        model=model,
        scaler=scaler,
        metadata=metadata,
        feature_block=feature_block,
    )


def compare_core_vs_specialist(
    df: pd.DataFrame,
    *,
    timeframe: str = "5m",
    label_column: str = DEFAULT_LABEL_COLUMN,
    purge_gap: int | None = None,
    min_train_samples: int = 120,
    min_test_samples: int = 40,
) -> dict[str, Any]:
    """Compare core-only vs core-plus-specialist feature sets."""
    prepared = _prepare_feature_sets(
        df,
        timeframe=timeframe,
        label_column=label_column,
    )
    comparison = compare_feature_sets(
        core_frame=prepared["core_frame"],
        core_feature_names=prepared["core_features"],
        candidate_frame=prepared["combined_frame"],
        candidate_feature_names=prepared["combined_features"],
        label_column=label_column,
        purge_gap=_resolve_purge_gap(purge_gap, prepared["label_horizon"]),
        min_train_samples=min_train_samples,
        min_test_samples=min_test_samples,
        specialist_name=DEFAULT_SPECIALIST_NAME,
    )
    comparison["feature_block"] = prepared["specialist_features"]
    comparison["timeframe"] = timeframe
    return comparison


def compare_feature_sets(
    *,
    core_frame: pd.DataFrame,
    core_feature_names: list[str],
    candidate_frame: pd.DataFrame,
    candidate_feature_names: list[str],
    label_column: str = DEFAULT_LABEL_COLUMN,
    purge_gap: int = 12,
    min_train_samples: int = 120,
    min_test_samples: int = 40,
    specialist_name: str = DEFAULT_SPECIALIST_NAME,
) -> dict[str, Any]:
    """Run a leak-free walk-forward comparison on aligned feature frames."""
    if len(core_frame) != len(candidate_frame):
        raise ValueError("Core and candidate feature frames must have identical length")
    if label_column not in core_frame.columns or label_column not in candidate_frame.columns:
        raise ValueError(f"Missing label column '{label_column}' in comparison frame")

    core_labels = core_frame[label_column].to_numpy(dtype=int)
    candidate_labels = candidate_frame[label_column].to_numpy(dtype=int)
    if not np.array_equal(core_labels, candidate_labels):
        raise ValueError("Core and candidate labels must be aligned")

    validator = WalkForwardValidator(
        purge_gap=purge_gap,
        min_train_samples=min_train_samples,
        min_test_samples=min_test_samples,
    )
    windows = validator.calculate_windows(len(core_frame))
    if not windows:
        raise ValueError(
            "No valid walk-forward windows for specialist comparison"
        )

    window_reports: list[dict[str, Any]] = []
    core_metrics: list[dict[str, float]] = []
    candidate_metrics: list[dict[str, float]] = []

    for window in windows:
        core_result = _train_window_model(
            core_frame,
            core_feature_names,
            label_column=label_column,
            window=window,
        )
        candidate_result = _train_window_model(
            candidate_frame,
            candidate_feature_names,
            label_column=label_column,
            window=window,
        )

        core_metrics.append(core_result["metrics"])
        candidate_metrics.append(candidate_result["metrics"])

        window_report = serialize_window_spec(window, purge_gap=purge_gap)
        window_report["scaler_scope"] = "train_only"
        window_report["core"] = core_result["metrics"]
        window_report["core_plus_specialist"] = candidate_result["metrics"]
        window_report["delta"] = _build_delta_metrics(
            core_result["metrics"],
            candidate_result["metrics"],
        )
        window_reports.append(window_report)

    core_summary = _aggregate_metrics(core_metrics)
    candidate_summary = _aggregate_metrics(candidate_metrics)

    return {
        "schema_version": 1,
        "specialist_name": specialist_name,
        "purge_gap": int(purge_gap),
        "window_count": len(window_reports),
        "comparison": {
            "core": core_summary,
            "core_plus_specialist": candidate_summary,
        },
        "deltas": _build_delta_metrics(core_summary, candidate_summary),
        "windows": window_reports,
    }


def _prepare_feature_sets(
    df: pd.DataFrame,
    *,
    timeframe: str,
    label_column: str,
) -> dict[str, Any]:
    engineer = FeatureEngineer()
    data_prep = DataPreparation()
    featured = engineer.create_features(
        df.copy(),
        timeframe=timeframe,
        include_specialist=True,
    )

    label_horizon = 12
    label_source = "provided"
    if label_column not in featured.columns:
        generator = LabelGenerator(
            tp_pips=18.0,
            sl_pips=12.0,
            max_candles=12,
            use_dynamic_atr=False,
        )
        featured[label_column] = generator.generate_labels(featured)
        label_horizon = int(generator.max_candles)
        label_source = "generated"

    warmup_candles = min(200, max(20, len(featured) // 5))
    featured = data_prep.remove_warmup_period(
        featured,
        warmup_candles=warmup_candles,
    )

    core_features = engineer.get_feature_names()
    specialist_features = engineer.get_specialist_feature_names()
    combined_features = core_features + specialist_features

    core_frame = featured[core_features + [label_column]].copy()
    combined_frame = featured[combined_features + [label_column]].copy()
    specialist_frame = featured[specialist_features + [label_column]].copy()

    return {
        "core_frame": core_frame,
        "combined_frame": combined_frame,
        "specialist_frame": specialist_frame,
        "core_features": core_features,
        "combined_features": combined_features,
        "specialist_features": specialist_features,
        "label_source": label_source,
        "label_horizon": label_horizon,
        "warmup_candles": warmup_candles,
    }


def _resolve_purge_gap(purge_gap: int | None, label_horizon: int) -> int:
    if purge_gap is not None:
        return int(max(1, purge_gap))
    return int(max(4, label_horizon))


def _train_eval_split(
    frame: pd.DataFrame,
    feature_names: list[str],
    *,
    label_column: str,
    purge_gap: int,
) -> dict[str, Any]:
    data_prep = DataPreparation()
    X, y = data_prep.prepare_features_labels(frame.copy(), feature_names, label_column)
    splits = data_prep.split_chronological(X, y, purge_gap=purge_gap)

    X_train, y_train = splits["train"]
    X_val, y_val = splits["val"]
    X_test, y_test = splits["test"]

    if len(X_train) < 30 or len(X_val) < 10 or len(X_test) < 10:
        raise ValueError("Insufficient split sizes for specialist training")

    train_df = pd.DataFrame(X_train, columns=feature_names)
    val_df = pd.DataFrame(X_val, columns=feature_names)
    test_df = pd.DataFrame(X_test, columns=feature_names)

    scaler = FeatureScaler()
    scaler.fit(train_df, feature_names)
    X_train_scaled = scaler.transform(train_df)[feature_names].values.astype(np.float32)
    X_val_scaled = scaler.transform(val_df)[feature_names].values.astype(np.float32)
    X_test_scaled = scaler.transform(test_df)[feature_names].values.astype(np.float32)

    model = LightGBMModel(
        {
            "n_estimators": 80,
            "learning_rate": 0.08,
            "n_jobs": 1,
            "random_state": 42,
        }
    )
    model.set_feature_names(feature_names)
    model.train(
        X_train_scaled,
        y_train,
        X_val_scaled,
        y_val,
        early_stopping_rounds=20,
        use_recency_weight=False,
    )

    probabilities = model.predict(X_test_scaled)
    metrics = _compute_prediction_metrics(probabilities, y_test)
    metrics["train_samples"] = int(len(X_train))
    metrics["val_samples"] = int(len(X_val))
    metrics["test_samples"] = int(len(X_test))

    return {
        "model": model,
        "scaler": scaler,
        "metrics": metrics,
        "split_sizes": {
            "train": int(len(X_train)),
            "val": int(len(X_val)),
            "test": int(len(X_test)),
        },
    }


def _train_window_model(
    frame: pd.DataFrame,
    feature_names: list[str],
    *,
    label_column: str,
    window: Any,
) -> dict[str, Any]:
    train_frame = frame.iloc[window.train_start:window.train_end].copy()
    test_frame = frame.iloc[window.test_start:window.test_end].copy()

    if len(train_frame) < 24 or len(test_frame) < 10:
        raise ValueError("Window too small for specialist comparison")

    val_size = max(8, int(len(train_frame) * 0.15))
    if val_size >= len(train_frame):
        raise ValueError("Validation split is larger than the training frame")

    fit_frame = train_frame.iloc[:-val_size].copy()
    val_frame = train_frame.iloc[-val_size:].copy()
    y_fit = fit_frame[label_column].to_numpy(dtype=int)
    y_val = val_frame[label_column].to_numpy(dtype=int)
    y_test = test_frame[label_column].to_numpy(dtype=int)

    if len(np.unique(y_fit)) < 2:
        raise ValueError("Training window needs at least two label classes")

    scaler = FeatureScaler()
    scaler.fit(fit_frame, feature_names)

    X_fit = scaler.transform(fit_frame)[feature_names].values.astype(np.float32)
    X_val = scaler.transform(val_frame)[feature_names].values.astype(np.float32)
    X_test = scaler.transform(test_frame)[feature_names].values.astype(np.float32)

    model = LightGBMModel(
        {
            "n_estimators": 60,
            "learning_rate": 0.08,
            "n_jobs": 1,
            "random_state": 42,
        }
    )
    model.set_feature_names(feature_names)
    model.train(
        X_fit,
        y_fit,
        X_val,
        y_val,
        early_stopping_rounds=15,
        use_recency_weight=False,
    )

    probabilities = model.predict(X_test)
    metrics = _compute_prediction_metrics(probabilities, y_test)
    metrics["fit_samples"] = int(len(fit_frame))
    metrics["validation_samples"] = int(len(val_frame))
    metrics["test_samples"] = int(len(test_frame))

    return {
        "metrics": metrics,
        "model": model,
        "scaler": scaler,
    }


def _compute_prediction_metrics(
    probabilities: np.ndarray,
    y_true: np.ndarray,
) -> dict[str, float]:
    if probabilities.size == 0:
        return {
            "accuracy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "calibration_score": 0.0,
            "trade_count": 0,
            "confidence_mean": 0.0,
        }

    probabilities = np.asarray(probabilities, dtype=float)
    predicted_idx = np.argmax(probabilities, axis=1)
    predicted_actions = predicted_idx - 1
    confidence = probabilities.max(axis=1)
    correct = (predicted_actions == y_true).astype(float)

    trade_mask = predicted_actions != 0
    trade_returns = np.where(
        trade_mask,
        np.where(predicted_actions == y_true, confidence, -confidence),
        0.0,
    )
    gross_profit = float(trade_returns[trade_returns > 0].sum())
    gross_loss = float(-trade_returns[trade_returns < 0].sum())
    profit_factor = gross_profit / max(gross_loss, 1e-6) if gross_profit > 0 else 0.0

    equity_curve = np.cumsum(trade_returns)
    peaks = np.maximum.accumulate(np.concatenate(([0.0], equity_curve)))
    drawdowns = peaks[1:] - equity_curve
    calibration_score = 1.0 - float(np.mean(np.abs(confidence - correct)))

    return {
        "accuracy": round(float(np.mean(correct)), 6),
        "profit_factor": round(float(profit_factor), 6),
        "max_drawdown": round(float(np.max(drawdowns) if len(drawdowns) else 0.0), 6),
        "calibration_score": round(float(calibration_score), 6),
        "trade_count": int(np.sum(trade_mask)),
        "confidence_mean": round(float(np.mean(confidence)), 6),
    }


def _aggregate_metrics(metrics_list: list[dict[str, float]]) -> dict[str, float]:
    if not metrics_list:
        return {
            "accuracy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "calibration_score": 0.0,
            "trade_count": 0,
            "confidence_mean": 0.0,
        }

    keys = ("accuracy", "profit_factor", "max_drawdown", "calibration_score", "confidence_mean")
    aggregated = {
        key: round(float(np.mean([metrics[key] for metrics in metrics_list])), 6)
        for key in keys
    }
    aggregated["trade_count"] = int(sum(int(metrics["trade_count"]) for metrics in metrics_list))
    return aggregated


def _build_delta_metrics(
    core_metrics: dict[str, float],
    candidate_metrics: dict[str, float],
) -> dict[str, float]:
    core_trades = max(float(core_metrics.get("trade_count", 0)), 1.0)
    return {
        "profit_factor_delta": round(
            float(candidate_metrics.get("profit_factor", 0.0) - core_metrics.get("profit_factor", 0.0)),
            6,
        ),
        "drawdown_delta": round(
            float(core_metrics.get("max_drawdown", 0.0) - candidate_metrics.get("max_drawdown", 0.0)),
            6,
        ),
        "calibration_delta": round(
            float(candidate_metrics.get("calibration_score", 0.0) - core_metrics.get("calibration_score", 0.0)),
            6,
        ),
        "trade_count_retention": round(
            float(candidate_metrics.get("trade_count", 0.0) / core_trades),
            6,
        ),
    }
