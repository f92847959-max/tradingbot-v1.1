"""Compatibility wrapper for the modular training loop package.

The implementation lives under scripts/training/ so the CLI remains stable:

    python scripts/train_loop.py
"""

from __future__ import annotations

from scripts.training.config import ASSETS, HISTORY_FILE, PROJECT_ROOT, PYTHON, SAVED_MODELS_DIR
from scripts.training.dashboard import Dashboard, format_duration
from scripts.training.history import latest_for_asset, load_history, save_history
from scripts.training.metrics import compute_improvements, extract_metrics, find_version_dir_after
from scripts.training.models import CycleResult
from scripts.training.process import (
    _active_proc,
    _force_stop_requested,
    _handle_sigint,
    _run_subprocess,
    _stop_requested,
    _subprocess_creation_flags,
    _subprocess_start_new_session,
    ensure_data,
)
from scripts.training.runner import build_parser, main, run_asset_cycle

__all__ = [
    "ASSETS",
    "Dashboard",
    "CycleResult",
    "HISTORY_FILE",
    "PROJECT_ROOT",
    "PYTHON",
    "SAVED_MODELS_DIR",
    "_active_proc",
    "_force_stop_requested",
    "_handle_sigint",
    "_run_subprocess",
    "_stop_requested",
    "_subprocess_creation_flags",
    "_subprocess_start_new_session",
    "build_parser",
    "compute_improvements",
    "ensure_data",
    "extract_metrics",
    "find_version_dir_after",
    "format_duration",
    "latest_for_asset",
    "load_history",
    "main",
    "run_asset_cycle",
    "save_history",
]


if __name__ == "__main__":
    main()
