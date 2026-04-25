"""Materialize decision snapshots into distillation datasets."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

import pandas as pd

from .decision_snapshot_capture import ACTION_TO_LABEL, DecisionSnapshot


def materialize_distill_dataset(
    snapshots: Iterable[DecisionSnapshot | dict[str, Any]],
    *,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Convert teacher snapshots into a tabular distillation dataset."""
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        payload = snapshot.to_dict() if isinstance(snapshot, DecisionSnapshot) else dict(snapshot)
        labels = payload.get("labels", {})
        row = dict(payload.get("observation", {}))
        row.update(
            {
                "timestamp": payload.get("timestamp", ""),
                "preliminary_action": payload.get("preliminary_action", "HOLD"),
                "policy_action": payload.get("policy_action", "HOLD"),
                "final_action": payload.get("final_action", "HOLD"),
                "block_stage": payload.get("block_stage", "none"),
                "block_codes": "|".join(payload.get("block_codes", [])),
                "preliminary_label": labels.get("preliminary_label", 1),
                "policy_label": labels.get("policy_label", 1),
                "final_label": labels.get("final_label", 1),
                "blocked": bool(labels.get("blocked", False)),
            }
        )
        rows.append(row)

    frame = pd.DataFrame(rows)
    feature_names = [
        column
        for column in frame.columns
        if column
        not in {
            "timestamp",
            "preliminary_action",
            "policy_action",
            "final_action",
            "block_stage",
            "block_codes",
            "preliminary_label",
            "policy_label",
            "final_label",
            "blocked",
        }
    ]
    manifest = {
        "schema_version": 1,
        "feature_names": feature_names,
        "label_columns": [
            "preliminary_label",
            "policy_label",
            "final_label",
            "blocked",
        ],
        "action_map": dict(ACTION_TO_LABEL),
    }
    label_summary = write_label_summary(frame)
    paths: dict[str, str] = {}
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        dataset_path = os.path.join(output_dir, "distill_dataset.csv")
        manifest_path = os.path.join(output_dir, "distill_dataset_manifest.json")
        summary_path = os.path.join(output_dir, "label_summary.json")
        frame.to_csv(dataset_path, index=False)
        _write_json(manifest_path, manifest)
        _write_json(summary_path, label_summary)
        paths = {
            "dataset": dataset_path,
            "manifest": manifest_path,
            "label_summary": summary_path,
        }
    return {
        "schema_version": 1,
        "frame": frame,
        "manifest": manifest,
        "label_summary": label_summary,
        "paths": paths,
    }


def write_label_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Return class and block-balance summaries for a distillation frame."""
    total = max(len(frame), 1)
    policy_counts = (
        frame.get("policy_action", pd.Series(dtype=str))
        .value_counts()
        .to_dict()
    )
    final_counts = (
        frame.get("final_action", pd.Series(dtype=str))
        .value_counts()
        .to_dict()
    )
    block_counts = (
        frame.get("block_stage", pd.Series(dtype=str))
        .value_counts()
        .to_dict()
    )
    blocked_hold_count = int(
        ((frame.get("blocked", False) == True) & (frame.get("final_action") == "HOLD")).sum()
    )
    return {
        "schema_version": 1,
        "total_samples": int(len(frame)),
        "policy_action_counts": {str(k): int(v) for k, v in policy_counts.items()},
        "final_action_counts": {str(k): int(v) for k, v in final_counts.items()},
        "block_stage_counts": {str(k): int(v) for k, v in block_counts.items()},
        "blocked_hold_count": blocked_hold_count,
        "blocked_hold_ratio": round(blocked_hold_count / total, 6),
        "capture_completeness": {
            "feature_columns": int(
                len(
                    [
                        column
                        for column in frame.columns
                        if column not in {"timestamp", "policy_action", "final_action"}
                    ]
                )
            ),
            "missing_policy_actions": int(frame.get("policy_action").isna().sum()) if "policy_action" in frame else 0,
        },
    }


def _write_json(path: str, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
