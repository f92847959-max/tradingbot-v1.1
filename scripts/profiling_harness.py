"""Profiling harness shared across CLI modes.

Two complementary profilers live here:

- `profile_call(callable, *args, mode_label=..., **kwargs)` — wraps any call in
  `cProfile.Profile()`. Writes a binary `.prof` file (loadable with snakeviz)
  and a human-readable top-N cumulative-time `.txt` summary next to it.
  Returns the wrapped call's return value.

- `maybe_pyspy_record(mode_label, pid, duration, output_dir)` — best-effort
  py-spy sampling profiler. Runs as a separate subprocess so it never leaks
  in-process state. Returns the speedscope output path or None when py-spy is
  not on PATH (the harness deliberately does NOT hard-require py-spy;
  cProfile is the baseline).

Output goes to `logs/profiling/<mode_label>_<utc-timestamp>.{prof,txt}` by
default. Timestamps are UTC `YYYYMMDD_HHMMSS` so multi-host runs sort
consistently.

This module must stay free of heavy ML imports (shap, lightgbm, matplotlib)
so it can be imported by `main.py --profile` without paying their startup
cost.
"""

from __future__ import annotations

import cProfile
import io
import logging
import os
import pstats
import shutil
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_OUTPUT_DIR = "logs/profiling"
DEFAULT_TOP_N = 30


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ensure_output_dir(output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def write_profile_report(
    stats: pstats.Stats,
    output_path: str,
    top_n: int = DEFAULT_TOP_N,
) -> None:
    """Write a formatted top-N cumulative-time text dump.

    Rebinds `stats.stream` to a StringIO so the report is captured rather
    than printed to stdout, then writes the captured text to `output_path`.
    Sort order: cumulative time, descending.
    """
    buffer = io.StringIO()
    stats.stream = buffer
    stats.sort_stats("cumulative")
    stats.print_stats(top_n)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())


def profile_call(
    callable_: Callable[..., T],
    *args: Any,
    mode_label: str,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    top_n: int = DEFAULT_TOP_N,
    **kwargs: Any,
) -> T:
    """Run `callable_(*args, **kwargs)` under cProfile and dump artifacts.

    Artifacts (created lazily on first call):
        {output_dir}/{mode_label}_{timestamp}.prof  -- binary cProfile dump
        {output_dir}/{mode_label}_{timestamp}.txt   -- top-N cumulative report

    The wrapped call's return value is returned unchanged. Exceptions
    propagate -- we still flush the .prof and .txt files in a `finally`
    block so a partial profile of a crash is preserved.
    """
    _ensure_output_dir(output_dir)
    ts = _timestamp_utc()
    prof_path = os.path.join(output_dir, f"{mode_label}_{ts}.prof")
    txt_path = os.path.join(output_dir, f"{mode_label}_{ts}.txt")

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        result = callable_(*args, **kwargs)
    finally:
        profiler.disable()
        try:
            profiler.dump_stats(prof_path)
        except Exception as exc:  # pragma: no cover - filesystem error path
            logger.warning("profiling_harness: dump_stats failed for %s: %s", prof_path, exc)
        try:
            stats = pstats.Stats(prof_path)
            write_profile_report(stats, txt_path, top_n=top_n)
        except Exception as exc:  # pragma: no cover - filesystem error path
            logger.warning("profiling_harness: write_profile_report failed: %s", exc)
        logger.info("profiling_harness: %s -> %s + %s", mode_label, prof_path, txt_path)
    return result


def maybe_pyspy_record(
    mode_label: str,
    pid: int | None = None,
    duration: int = 60,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> str | None:
    """Best-effort py-spy sampling profile.

    Returns the speedscope output path on success, or None when py-spy is
    not on PATH (we deliberately do NOT hard-require py-spy -- cProfile
    is the baseline). When `pid` is None, py-spy records the calling
    process itself.

    Runs py-spy as a subprocess so its sampler never leaves in-process
    state behind.
    """
    py_spy = shutil.which("py-spy")
    if not py_spy:
        logger.info("py-spy not on PATH; skipping sampling profile (cProfile remains active).")
        return None

    _ensure_output_dir(output_dir)
    ts = _timestamp_utc()
    out_path = os.path.join(output_dir, f"{mode_label}_{ts}.speedscope.json")
    target_pid = pid if pid is not None else os.getpid()

    cmd = [
        py_spy,
        "record",
        "--format", "speedscope",
        "--output", out_path,
        "--duration", str(int(duration)),
        "--pid", str(int(target_pid)),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as exc:
        logger.warning("py-spy invocation failed: %s", exc)
        return None
    if result.returncode != 0:
        logger.warning(
            "py-spy returned %s: %s", result.returncode, result.stderr.strip()
        )
        return None
    logger.info("py-spy sample profile written to %s", out_path)
    return out_path


__all__ = ["profile_call", "write_profile_report", "maybe_pyspy_record"]
