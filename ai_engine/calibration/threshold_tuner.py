"""Regime-aware confidence threshold tuning helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

import numpy as np

from strategy.regime_detector import MarketRegime

from ..training.trade_filter import probs_to_trade_signals
from .artifacts import CLASS_LABELS

ACTION_TO_SIGNAL = {"SELL": -1, "HOLD": 0, "BUY": 1}
DEFAULT_CONFIDENCE_GRID = (0.34, 0.40, 0.46, 0.52, 0.58, 0.64, 0.70)
DEFAULT_MARGIN_GRID = (0.00, 0.03, 0.06, 0.09, 0.12)


def _ensure_class_labels(y_true: np.ndarray) -> np.ndarray:
    labels = np.asarray(y_true, dtype=np.int64)
    if labels.min() < 0:
        labels = labels + 1
    if labels.min() < 0 or labels.max() > 2:
        raise ValueError("y_true must be in signal-space [-1, 0, 1] or class-space [0, 1, 2]")
    return labels


def _ensure_probabilities(y_probs: np.ndarray) -> np.ndarray:
    probs = np.asarray(y_probs, dtype=np.float64)
    if probs.ndim != 2 or probs.shape[1] != 3:
        raise ValueError("y_probs must have shape [n_samples, 3]")
    row_sums = probs.sum(axis=1, keepdims=True)
    safe_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return np.clip(probs / safe_sums, 1e-9, 1.0)


def _normalize_regime(value: Any) -> str:
    if isinstance(value, MarketRegime):
        return value.value
    text = str(value or "global").strip().lower()
    if text in {"trending", "ranging", "volatile"}:
        return text
    return "global"


def _score_thresholds(
    *,
    y_true_signal: np.ndarray,
    y_probs: np.ndarray,
    action_label: str,
    confidence_grid: Iterable[float],
    margin_grid: Iterable[float],
    min_support: int,
) -> dict[str, Any]:
    action_signal = ACTION_TO_SIGNAL[action_label]
    best: dict[str, Any] | None = None
    best_rank: tuple[float, float, float, float, float, float] | None = None

    for min_confidence in confidence_grid:
        for min_margin in margin_grid:
            signals = probs_to_trade_signals(
                y_probs,
                min_confidence=float(min_confidence),
                min_margin=float(min_margin),
            )
            predicted_mask = signals == action_signal
            support = int(predicted_mask.sum())
            tp = int(np.sum(predicted_mask & (y_true_signal == action_signal)))
            fp = int(np.sum(predicted_mask & (y_true_signal != action_signal)))
            fn = int(np.sum((~predicted_mask) & (y_true_signal == action_signal)))

            precision = tp / support if support else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            f1 = (
                (2.0 * precision * recall) / (precision + recall)
                if (precision + recall)
                else 0.0
            )
            enough_support = 1.0 if support >= min_support else 0.0
            rank = (
                enough_support,
                f1,
                precision,
                recall,
                float(support),
                -float(min_confidence),
            )
            if best is None or best_rank is None or rank > best_rank:
                best = {
                    "action": action_label,
                    "min_confidence": float(min_confidence),
                    "min_margin": float(min_margin),
                    "support": support,
                    "precision": float(precision),
                    "recall": float(recall),
                    "f1": float(f1),
                }
                best_rank = rank

    assert best is not None
    return best


def tune_thresholds(
    *,
    y_true: np.ndarray,
    y_probs: np.ndarray,
    regimes: Iterable[Any] | None = None,
    model_name: str = "model",
    min_support: int | None = None,
    confidence_grid: Iterable[float] = DEFAULT_CONFIDENCE_GRID,
    margin_grid: Iterable[float] = DEFAULT_MARGIN_GRID,
) -> dict[str, Any]:
    probs = _ensure_probabilities(y_probs)
    labels = _ensure_class_labels(y_true)
    y_true_signal = labels - 1

    if min_support is None:
        min_support = max(8, int(len(labels) * 0.08))

    regime_values = (
        np.asarray([_normalize_regime(value) for value in regimes], dtype=object)
        if regimes is not None
        else np.asarray(["global"] * len(labels), dtype=object)
    )
    if len(regime_values) != len(labels):
        raise ValueError("regimes length must match y_true length")

    thresholds: dict[str, dict[str, Any]] = {}
    sample_counts: dict[str, int] = {"global": int(len(labels))}

    global_table = {
        action: _score_thresholds(
            y_true_signal=y_true_signal,
            y_probs=probs,
            action_label=action,
            confidence_grid=confidence_grid,
            margin_grid=margin_grid,
            min_support=int(min_support),
        )
        for action in ("SELL", "BUY")
    }
    thresholds["global"] = global_table

    for regime_key in ("trending", "ranging", "volatile"):
        mask = regime_values == regime_key
        sample_count = int(mask.sum())
        sample_counts[regime_key] = sample_count
        if sample_count < int(min_support):
            continue
        thresholds[regime_key] = {
            action: _score_thresholds(
                y_true_signal=y_true_signal[mask],
                y_probs=probs[mask],
                action_label=action,
                confidence_grid=confidence_grid,
                margin_grid=margin_grid,
                min_support=max(3, int(min_support // 2)),
            )
            for action in ("SELL", "BUY")
        }

    defaults = {
        action: {
            "action": action,
            "min_confidence": float(global_table[action]["min_confidence"]),
            "min_margin": float(global_table[action]["min_margin"]),
        }
        for action in ("SELL", "BUY")
    }
    defaults["HOLD"] = {
        "action": "HOLD",
        "min_confidence": 1.0,
        "min_margin": 0.0,
    }

    return {
        "schema_version": 1,
        "class_labels": list(CLASS_LABELS),
        "source": {
            "model_name": model_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "min_support": int(min_support),
        },
        "fallback_order": ["exact", "global", "ranging", "defaults"],
        "sample_counts": sample_counts,
        "defaults": defaults,
        "thresholds": thresholds,
    }


def lookup_threshold(
    threshold_artifact: dict[str, Any],
    *,
    regime: Any,
    action: str,
) -> dict[str, Any]:
    action_key = str(action).upper()
    if action_key not in {"SELL", "HOLD", "BUY"}:
        raise ValueError(f"Unsupported action: {action}")

    regime_key = _normalize_regime(regime)
    defaults = dict(threshold_artifact.get("defaults", {}).get(action_key, {}))

    if action_key == "HOLD":
        defaults.setdefault("action", "HOLD")
        defaults.setdefault("min_confidence", 1.0)
        defaults.setdefault("min_margin", 0.0)
        defaults["threshold_source"] = "hold-default"
        defaults["regime"] = regime_key
        return defaults

    thresholds = threshold_artifact.get("thresholds", {})
    search_order = [regime_key, "global", "ranging"]
    for source in search_order:
        source_table = thresholds.get(source, {})
        if action_key in source_table:
            result = dict(source_table[action_key])
            result["threshold_source"] = source
            result["regime"] = regime_key
            return result

    if defaults:
        defaults["threshold_source"] = "defaults"
        defaults["regime"] = regime_key
        return defaults

    raise KeyError(f"No threshold found for action={action_key} regime={regime_key}")
