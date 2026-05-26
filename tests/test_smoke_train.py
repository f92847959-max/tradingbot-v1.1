"""Smoke-train tests for `main.py train --smoke` (Phase 18 D-19 / Plan 18-04).

The smoke run trains a single synthetic 2000-candle 5m dataset into a throwaway
temp dir, bypassing the 48-month production floor, and must finish well under
60 seconds without polluting ai_engine/saved_models.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAVED_MODELS = REPO_ROOT / "ai_engine" / "saved_models"


def _version_dirs() -> set[str]:
    if not SAVED_MODELS.is_dir():
        return set()
    return {
        p.name for p in SAVED_MODELS.iterdir() if p.is_dir() and p.name.startswith("v")
    }


@pytest.mark.slow
def test_smoke_completes_in_under_60s_and_no_pollution():
    """`main.py train --smoke` exits 0, prints SMOKE PASSED, runs < 60s, and
    creates no new version dir under ai_engine/saved_models."""
    before = _version_dirs()
    start = time.time()
    proc = subprocess.run(
        [sys.executable, "main.py", "train", "--smoke"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    elapsed = time.time() - start
    after = _version_dirs()

    combined = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"smoke exited {proc.returncode}:\n{combined[-2000:]}"
    assert "SMOKE PASSED" in combined, f"missing SMOKE PASSED:\n{combined[-2000:]}"
    assert elapsed < 60.0, f"smoke took {elapsed:.1f}s (>= 60s budget)"
    assert before == after, (
        f"smoke polluted saved_models: new dirs = {sorted(after - before)}"
    )


def test_smoke_synthetic_dataset_bypasses_48_month_floor():
    """The 2000-candle synthetic dataset is ~7 days -> far below the 48-month
    floor. The smoke path bypasses the floor by passing --allow-short-data,
    which makes scripts/train_models.py SKIP the calculate_trainable_span
    preflight entirely. We assert (a) the floor WOULD trip without the bypass
    and (b) the smoke run command actually carries --allow-short-data."""
    from scripts.train_models import generate_synthetic_data
    from ai_engine.training.data_coverage import (
        DEFAULT_MIN_MONTHS_PROD,
        DataCoverageError,
        calculate_trainable_span,
    )

    df = generate_synthetic_data(2000)
    assert len(df) == 2000

    # Without the bypass, the prod floor (48mo) trips on a 7-day dataset.
    with pytest.raises(DataCoverageError):
        calculate_trainable_span(df, min_months=DEFAULT_MIN_MONTHS_PROD)

    # The smoke runner must pass --allow-short-data so the preflight is skipped.
    import inspect

    import start_ai_training

    smoke_src = inspect.getsource(start_ai_training._run_smoke)
    assert "--allow-short-data" in smoke_src
    assert "--synthetic" in smoke_src


def test_smoke_flag_present_on_train_surface():
    """`--smoke` must be exposed on the canonical training flag surface."""
    from start_ai_training import _build_parser

    help_text = _build_parser().format_help()
    assert "--smoke" in help_text
    assert "--device" in help_text
    assert "--allow-short-data" in help_text
