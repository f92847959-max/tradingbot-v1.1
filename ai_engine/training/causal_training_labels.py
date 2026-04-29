"""Causal training label and split manifest helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .label_generator import LabelGenerator
from .walk_forward import serialize_window_spec


@dataclass(frozen=True)
class CausalLabelConfig:
    """Configuration captured in label manifests."""

    schema_version: int = 1
    entry_label_source: str = "LabelGenerator.generate_labels"
    max_holding_candles: int = 60
    spread_pips: float = 2.5
    risk_column: str = "atr_14"
    exit_label_column: str | None = None

    @classmethod
    def from_label_generator(
        cls,
        label_generator: LabelGenerator,
        **overrides: Any,
    ) -> "CausalLabelConfig":
        payload = {
            "max_holding_candles": int(getattr(label_generator, "max_candles", 60)),
            "spread_pips": float(getattr(label_generator, "spread_pips", 2.5)),
        }
        payload.update(overrides)
        return cls(**payload)


def build_causal_label_frame(
    df: pd.DataFrame,
    label_generator: LabelGenerator,
    config: CausalLabelConfig | None = None,
) -> pd.DataFrame:
    """Build explicit label columns without adding future outcome features."""
    cfg = config or CausalLabelConfig.from_label_generator(label_generator)
    entry_label = pd.Series(
        label_generator.generate_labels(df),
        index=df.index,
        name="entry_label",
    ).astype(int)

    labels = pd.DataFrame(index=df.index)
    labels["entry_label"] = entry_label
    labels["abstain_label"] = (entry_label == 0).astype(int)

    if cfg.exit_label_column and cfg.exit_label_column in df.columns:
        labels["exit_label"] = df[cfg.exit_label_column].astype(str).values
    else:
        labels["exit_label"] = "UNAVAILABLE"

    labels["confidence_target"] = (entry_label != 0).astype(float)
    labels["risk_bucket"] = _risk_buckets(df, cfg.risk_column)
    return labels


def build_label_manifest(
    config: CausalLabelConfig,
    label_columns: list[str],
) -> dict[str, Any]:
    """Return a stable label schema manifest."""
    return {
        "schema_version": config.schema_version,
        "label_columns": list(label_columns),
        "entry_label_source": config.entry_label_source,
        "max_holding_candles": config.max_holding_candles,
        "spread_pips": config.spread_pips,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_split_manifest(
    windows: list[Any],
    *,
    purge_gap: int,
    feature_names: list[str],
    label_columns: list[str],
) -> dict[str, Any]:
    """Serialize walk-forward windows and model input schema."""
    label_set = set(label_columns)
    clean_features = [name for name in feature_names if name not in label_set]
    return {
        "schema_version": 1,
        "purge_gap": int(purge_gap),
        "window_count": len(windows),
        "feature_names": clean_features,
        "label_columns": list(label_columns),
        "windows": [
            _serialize_window(window, index, purge_gap)
            for index, window in enumerate(windows)
        ],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _risk_buckets(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(["unknown"] * len(df), index=df.index, dtype="object")

    values = pd.to_numeric(df[column], errors="coerce")
    valid = values.dropna()
    if valid.empty or valid.nunique() < 3:
        return pd.Series(["unknown"] * len(df), index=df.index, dtype="object")

    low = valid.quantile(1.0 / 3.0)
    high = valid.quantile(2.0 / 3.0)

    def bucket(value: float) -> str:
        if pd.isna(value):
            return "unknown"
        if value <= low:
            return "low"
        if value <= high:
            return "medium"
        return "high"

    return values.map(bucket).astype("object")


def _serialize_window(window: Any, index: int, purge_gap: int) -> dict[str, Any]:
    if hasattr(window, "window_id"):
        return serialize_window_spec(window, purge_gap=purge_gap)
    if isinstance(window, dict):
        payload = dict(window)
        payload.setdefault("purge_gap", int(purge_gap))
        return payload
    return {
        "window_id": int(index),
        "window_ref": str(window),
        "purge_gap": int(purge_gap),
    }
