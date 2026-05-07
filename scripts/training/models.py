"""Data containers for training loop state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CycleResult:
    cycle: int
    asset: str
    started_at: str
    duration_sec: float
    version_dir: str
    core_ai: dict[str, Any] = field(default_factory=dict)
    exit_ai: dict[str, Any] = field(default_factory=dict)
    backtest: dict[str, Any] = field(default_factory=dict)
    improvements_pct: dict[str, float] = field(default_factory=dict)
