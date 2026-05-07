"""Metric loading and comparison helpers for the training loop."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .config import SAVED_MODELS_DIR
from .models import CycleResult


def find_version_dir_after(timestamp: float) -> Path | None:
    if not SAVED_MODELS_DIR.exists():
        return None
    candidates = [
        p
        for p in SAVED_MODELS_DIR.iterdir()
        if p.is_dir()
        and p.name.startswith("v")
        and "_" in p.name
        and p.stat().st_mtime >= timestamp
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def extract_metrics(version_dir: Path) -> dict[str, dict[str, Any]]:
    train_report = _read_json(version_dir / "training_report.json")
    backtest_report = _read_json(version_dir / "backtest_report.json")

    exit_promotion: dict[str, Any] = {}
    specialist_root = SAVED_MODELS_DIR / "specialists" / "exit_ai"
    if specialist_root.exists():
        exit_versions = [
            p for p in specialist_root.iterdir() if p.is_dir() and p.name.startswith("v")
        ]
        if exit_versions:
            latest_exit = max(exit_versions, key=lambda p: p.stat().st_mtime)
            exit_promotion = _read_json(latest_exit / "exit_ai_promotion_artifact.json")

    aggregate = train_report.get("aggregate", {})
    bt_aggregate = backtest_report.get("aggregate", {})
    eval_cand = exit_promotion.get("evaluation", {}).get("candidate_metrics", {})

    return {
        "core_ai": {
            "xgboost": _flatten_core(aggregate.get("xgboost", {})),
            "lightgbm": _flatten_core(aggregate.get("lightgbm", {})),
            "best_model": aggregate.get("best_model", ""),
        },
        "exit_ai": {
            "promotion_status": exit_promotion.get("promotion_status", "N/A"),
            "accuracy": _as_float(eval_cand.get("accuracy")),
            "calibration_score": _as_float(eval_cand.get("calibration_score")),
            "profit_factor_proxy": _as_float(eval_cand.get("profit_factor_proxy")),
            "trade_retention": _as_float(eval_cand.get("trade_retention")),
        },
        "backtest": {
            "profit_factor": _as_float(bt_aggregate.get("profit_factor")),
            "sharpe_ratio": _as_float(bt_aggregate.get("sharpe_ratio")),
            "win_rate": _as_float(bt_aggregate.get("win_rate")),
            "total_pips": _as_float(bt_aggregate.get("total_pips")),
            "max_drawdown_pct": _as_float(bt_aggregate.get("max_drawdown_pct")),
            "n_trades": int(
                bt_aggregate.get("total_trades", bt_aggregate.get("n_trades", 0)) or 0
            ),
        },
    }


def compute_improvements(current: dict, previous: dict) -> dict[str, float]:
    if not previous:
        return {}
    deltas: dict[str, float] = {}

    def walk(prefix: str, cur: Any, prev: Any) -> None:
        if isinstance(cur, dict) and isinstance(prev, dict):
            for k in cur:
                if k in prev:
                    walk(f"{prefix}.{k}" if prefix else k, cur[k], prev[k])
        elif isinstance(cur, (int, float)) and isinstance(prev, (int, float)):
            if not math.isfinite(float(cur)) or not math.isfinite(float(prev)):
                return
            if prev == 0:
                deltas[prefix] = 0.0 if cur == 0 else 100.0
            else:
                deltas[prefix] = ((cur - prev) / abs(prev)) * 100.0

    walk("", current, previous)
    return deltas


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def _as_float(v: Any, default: float = 0.0) -> float:
    if isinstance(v, (int, float)):
        f = float(v)
        if math.isfinite(f):
            return f
    return default


def _flatten_core(model_metrics: dict[str, Any]) -> dict[str, float]:
    return {
        "win_rate": model_metrics.get("win_rate", 0.0),
        "profit_factor": model_metrics.get("profit_factor", 0.0),
        "sharpe": model_metrics.get("sharpe", 0.0),
        "expectancy": model_metrics.get("expectancy", 0.0),
        "n_trades": model_metrics.get("n_trades", 0),
    }


def dig(d: dict | CycleResult | None, keys: list[str]) -> Any:
    if d is None:
        return None
    cur: Any = d.__dict__ if isinstance(d, CycleResult) else d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur
