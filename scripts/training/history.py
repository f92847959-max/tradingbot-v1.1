"""History persistence for the continuous training loop."""

from __future__ import annotations

import json
import math
from typing import Any

from .config import HISTORY_FILE
from .models import CycleResult


def load_history() -> list[CycleResult]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open(encoding="utf-8") as f:
            data = json.load(f)
        return [_sanitize_cycle(CycleResult(**entry)) for entry in data]
    except (json.JSONDecodeError, TypeError):
        return []


def save_history(history: list[CycleResult]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("w", encoding="utf-8") as f:
        json.dump(
            [_sanitize_cycle(h).__dict__ for h in history],
            f,
            indent=2,
            allow_nan=False,
        )


def latest_for_asset(history: list[CycleResult], asset: str) -> CycleResult | None:
    for entry in reversed(history):
        if entry.asset == asset:
            return entry
    return None


def _sanitize_cycle(result: CycleResult) -> CycleResult:
    result.core_ai = _sanitize_value(result.core_ai)
    result.exit_ai = _sanitize_value(result.exit_ai)
    result.backtest = _sanitize_value(result.backtest)
    result.improvements_pct = _sanitize_value(result.improvements_pct)
    return result


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return value
