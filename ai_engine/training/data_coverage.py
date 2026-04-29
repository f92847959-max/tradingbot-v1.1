"""Dataset coverage and manifest helpers for training preflight."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


class DataCoverageError(ValueError):
    """Raised when a dataset is too short for the configured training span."""


_STAGES = ["received", "saved", "normalized", "feature_ready", "label_ready"]


def _timestamps(df: pd.DataFrame) -> pd.Series:
    if "timestamp" in df.columns:
        values = df["timestamp"]
    elif isinstance(df.index, pd.DatetimeIndex):
        values = pd.Series(df.index, index=df.index)
    else:
        values = pd.Series([], dtype="datetime64[ns, UTC]")
    ts = pd.to_datetime(values, utc=True, errors="coerce").dropna()
    return ts.sort_values().reset_index(drop=True)


def _span_payload(df: pd.DataFrame, min_months: int = 6) -> dict[str, Any]:
    ts = _timestamps(df)
    rows = int(len(df))
    minimum_days = float(min_months) * 30.44

    if len(ts) < 2:
        return {
            "rows": rows,
            "trainable_days": 0.0,
            "trainable_hours": 0.0,
            "available_months": 0.0,
            "minimum_days": minimum_days,
            "start_timestamp": ts.iloc[0].isoformat() if len(ts) == 1 else None,
            "end_timestamp": ts.iloc[-1].isoformat() if len(ts) == 1 else None,
        }

    start = ts.iloc[0]
    end = ts.iloc[-1]
    hours = (end - start).total_seconds() / 3600.0
    days = hours / 24.0
    return {
        "rows": rows,
        "trainable_days": round(days, 6),
        "trainable_hours": round(hours, 6),
        "available_months": round(days / 30.44, 6),
        "minimum_days": minimum_days,
        "start_timestamp": start.isoformat(),
        "end_timestamp": end.isoformat(),
    }


def calculate_trainable_span(
    df: pd.DataFrame,
    min_months: int = 6,
) -> dict[str, Any]:
    """Return trainable span metadata and fail if it is below min_months."""
    payload = _span_payload(df, min_months=min_months)
    if payload["trainable_days"] < payload["minimum_days"]:
        raise DataCoverageError(
            "Insufficient trainable history: "
            f"trainable_days={payload['trainable_days']} "
            f"minimum_days={payload['minimum_days']} "
            f"start_timestamp={payload['start_timestamp']} "
            f"end_timestamp={payload['end_timestamp']} "
            f"rows={payload['rows']}"
        )
    return payload


def build_row_loss_report(stage_counts: dict[str, int]) -> dict[str, Any]:
    """Build ordered row-loss telemetry between training data stages."""
    counts = {stage: int(stage_counts.get(stage, 0)) for stage in _STAGES}
    transitions: list[dict[str, Any]] = []
    dropped_rows: dict[str, int] = {}

    for left, right in zip(_STAGES, _STAGES[1:]):
        from_rows = counts[left]
        to_rows = counts[right]
        dropped = max(from_rows - to_rows, 0)
        key = f"{left}_to_{right}"
        dropped_rows[key] = dropped
        transitions.append(
            {
                "name": key,
                "from": left,
                "to": right,
                "from_rows": from_rows,
                "to_rows": to_rows,
                "dropped_rows": dropped,
                "drop_pct": round((dropped / from_rows) * 100.0, 6)
                if from_rows
                else 0.0,
                "reason": f"{left}_to_{right}",
            }
        )

    return {
        "stage_counts": counts,
        "transitions": transitions,
        "dropped_rows": dropped_rows,
        "total_dropped_rows": sum(dropped_rows.values()),
    }


def build_dataset_manifest(
    source_details: dict[str, Any],
    df: pd.DataFrame,
    row_loss: dict[str, Any],
    *,
    feature_set: str,
    label_set: str,
    min_months: int,
) -> dict[str, Any]:
    """Build a JSON-serializable dataset manifest."""
    span = _span_payload(df, min_months=min_months)
    counts = row_loss.get("stage_counts", {})
    return {
        "source": source_details.get("source", "unknown"),
        "timeframe": source_details.get("timeframe", "unknown"),
        "feature_set": feature_set,
        "label_set": label_set,
        "received_rows": int(counts.get("received", len(df))),
        "saved_rows": int(counts.get("saved", len(df))),
        "normalized_rows": int(counts.get("normalized", len(df))),
        "feature_ready_rows": int(counts.get("feature_ready", len(df))),
        "label_ready_rows": int(counts.get("label_ready", len(df))),
        "trainable_days": span["trainable_days"],
        "trainable_hours": span["trainable_hours"],
        "available_months": span["available_months"],
        "minimum_days": span["minimum_days"],
        "start_timestamp": span["start_timestamp"],
        "end_timestamp": span["end_timestamp"],
        "dropped_rows": row_loss.get("dropped_rows", {}),
        "row_loss": row_loss,
        "source_details": dict(source_details),
    }


def write_dataset_manifest(manifest: dict[str, Any], path: str | Path) -> str:
    """Write a dataset manifest as UTF-8 JSON and return the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(out)
