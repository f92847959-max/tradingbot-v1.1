"""Configuration constants for the continuous training loop."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVED_MODELS_DIR = PROJECT_ROOT / "ai_engine" / "saved_models"
HISTORY_FILE = PROJECT_ROOT / "logs" / "training_loop_history.json"

ASSETS: dict[str, dict[str, Any]] = {
    "gold": {
        "csv": "data/gold_1h.csv",
        "pip_size": 0.01,
        "label": "Gold",
        "tp_pips": 1500.0,
        "sl_pips": 800.0,
    },
    "silver": {
        "csv": "data/silver_1h.csv",
        "pip_size": 0.001,
        "label": "Silber",
        "tp_pips": 200.0,
        "sl_pips": 100.0,
    },
}


def resolve_python() -> str:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    venv_python_unix = PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python_unix.exists():
        return str(venv_python_unix)
    return sys.executable


PYTHON = resolve_python()
