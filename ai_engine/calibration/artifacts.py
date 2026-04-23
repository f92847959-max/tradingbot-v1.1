"""JSON artifact helpers for calibration and decision thresholds."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

CLASS_LABELS = ["SELL", "HOLD", "BUY"]


def _resolve_artifact_path(path_or_dir: str, filename: str) -> str:
    if os.path.isdir(path_or_dir):
        return os.path.join(path_or_dir, filename)
    return path_or_dir


def _validate_class_labels(payload: Mapping[str, Any]) -> None:
    class_labels = list(payload.get("class_labels", []))
    if class_labels != CLASS_LABELS:
        raise ValueError(
            f"class_labels must be {CLASS_LABELS}, got {class_labels!r}"
        )


def _validate_threshold_payload(payload: Mapping[str, Any]) -> None:
    if int(payload.get("schema_version", 0) or 0) < 1:
        raise ValueError("threshold artifact schema_version must be >= 1")
    _validate_class_labels(payload)
    thresholds = payload.get("thresholds")
    models = payload.get("models")
    if isinstance(thresholds, dict) and thresholds:
        return
    if isinstance(models, dict) and models:
        for model_payload in models.values():
            nested_thresholds = model_payload.get("thresholds")
            if not isinstance(nested_thresholds, dict) or not nested_thresholds:
                raise ValueError(
                    "aggregate threshold artifact models must each contain thresholds"
                )
        return
    raise ValueError("threshold artifact must contain non-empty thresholds")


def _validate_calibration_payload(payload: Mapping[str, Any]) -> None:
    if int(payload.get("schema_version", 0) or 0) < 1:
        raise ValueError("calibration artifact schema_version must be >= 1")
    _validate_class_labels(payload)
    models = payload.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("calibration artifact must contain non-empty models")


def _write_json(path: str, payload: Mapping[str, Any]) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return path


def write_calibration_artifact(
    version_dir: str,
    calibration_data: Mapping[str, Any],
) -> str:
    payload = dict(calibration_data)
    payload.setdefault("schema_version", 1)
    payload.setdefault("class_labels", CLASS_LABELS)
    models = payload.get("models", {})
    if isinstance(models, dict):
        sanitized = {}
        for name, model_payload in models.items():
            entry = dict(model_payload)
            calibrator_path = entry.get("calibrator_path")
            if calibrator_path:
                entry["calibrator_path"] = os.path.basename(str(calibrator_path))
            sanitized[str(name).lower()] = entry
        payload["models"] = sanitized
    _validate_calibration_payload(payload)
    return _write_json(os.path.join(version_dir, "calibration.json"), payload)


def write_threshold_artifact(
    version_dir: str,
    threshold_data: Mapping[str, Any],
) -> str:
    payload = dict(threshold_data)
    payload.setdefault("schema_version", 1)
    payload.setdefault("class_labels", CLASS_LABELS)
    _validate_threshold_payload(payload)
    return _write_json(os.path.join(version_dir, "thresholds.json"), payload)


def load_calibration_artifact(path_or_dir: str) -> dict[str, Any]:
    path = _resolve_artifact_path(path_or_dir, "calibration.json")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    _validate_calibration_payload(payload)
    return payload


def load_threshold_artifact(path_or_dir: str) -> dict[str, Any]:
    path = _resolve_artifact_path(path_or_dir, "thresholds.json")
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    _validate_threshold_payload(payload)
    return payload
