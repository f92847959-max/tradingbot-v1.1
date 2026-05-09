"""Configuration for the terminal UI demo."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_PATH = REPO_ROOT / "logs" / "ui_demo" / "KI_ANALYSE_REPORT.txt"


@dataclass(frozen=True)
class DemoConfig:
    max_epochs: int = 150
    history_len: int = 50
    refresh_per_second: int = 8
    step_delay_sec: float = 0.02
    llm_timeout_sec: float = 60.0
    llm_enabled: bool = True
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    report_path: Path = DEFAULT_REPORT_PATH
    screen: bool = True

    @classmethod
    def from_env(cls) -> "DemoConfig":
        return cls(
            max_epochs=_env_int("UI_DEMO_MAX_EPOCHS", cls.max_epochs),
            history_len=_env_int("UI_DEMO_HISTORY_LEN", cls.history_len),
            refresh_per_second=_env_int(
                "UI_DEMO_REFRESH_PER_SECOND",
                cls.refresh_per_second,
            ),
            step_delay_sec=_env_float("UI_DEMO_STEP_DELAY_SEC", cls.step_delay_sec),
            llm_timeout_sec=_env_float("UI_DEMO_LLM_TIMEOUT_SEC", cls.llm_timeout_sec),
            llm_enabled=_env_bool("UI_DEMO_LLM_ENABLED", cls.llm_enabled),
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
            gemini_model=os.environ.get("UI_DEMO_GEMINI_MODEL", cls.gemini_model),
            report_path=Path(
                os.environ.get("UI_DEMO_REPORT_PATH", str(DEFAULT_REPORT_PATH)),
            ),
            screen=_env_bool("UI_DEMO_SCREEN", cls.screen),
        )

    def with_overrides(self, **overrides: Any) -> "DemoConfig":
        clean = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **clean)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", ""}
