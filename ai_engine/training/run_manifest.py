"""Run-manifest sidecar for training runs (Phase 18 D-17).

The run manifest is an **additive** JSON sidecar written next to ``version.json``
inside each training version directory. It captures full reproducibility
context (seed, git SHA, data hash, pip-freeze digest, Python version, CPU/GPU
info, per-stage wall-clock, cache hit rate, walk-forward window count) without
touching ``version.json`` — the Phase 12.7 promotion gate sees an identical
``version.json`` schema to today.

Public API:
    - ``build_run_manifest(...) -> dict``
    - ``write_run_manifest(manifest, version_dir) -> str``

Helper functions (prefixed ``_``) are exposed for unit testing but are not part
of the stable contract.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
PHASE = "18"
MANIFEST_FILENAME = "run_manifest.json"


def _compute_git_sha() -> str:
    """Return the current commit SHA.

    Appends ``+dirty{N}`` (N = count of changed/untracked entries from
    ``git status --porcelain``) when the working tree has uncommitted
    changes, so a manifest can never silently claim a clean checkout.
    Returns ``"unknown"`` when git is unavailable or the cwd is not a repo.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if sha.returncode != 0:
            return "unknown"
        head = sha.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if status.returncode == 0 and status.stdout.strip():
            dirty_count = len(
                [ln for ln in status.stdout.splitlines() if ln.strip()]
            )
            return f"{head}+dirty{dirty_count}"
        return head
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _compute_pip_freeze_digest() -> str:
    """Return a SHA256 digest of ``pip freeze`` output (the installed env).

    Returns ``"unknown"`` when pip cannot be invoked.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return "unknown"
        digest = hashlib.sha256(result.stdout.encode("utf-8")).hexdigest()
        return f"sha256:{digest}"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _compute_data_hash(csv_path: str | Path | None) -> str | None:
    """Return ``sha256:<hex>`` of the input CSV bytes, or ``None``.

    ``None`` is returned when no path is given (e.g. broker/in-memory source)
    or the file does not exist.
    """
    if csv_path is None:
        return None
    path = Path(csv_path)
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _cpu_info() -> dict[str, Any]:
    """Return a small dict describing the host CPU."""
    return {
        "processor": platform.processor() or "unknown",
        "machine": platform.machine() or "unknown",
        "logical_cores": os.cpu_count(),
        "platform": platform.platform(),
    }


def build_run_manifest(
    *,
    seed: int,
    timeframe: str,
    data_csv_path: str | Path | None,
    fetched_months: float,
    n_windows: int,
    device: str,
    gpu_info: dict[str, Any] | None,
    wall_clock_stages: dict[str, float],
    cache_hit_rate: float | None,
    parallel_windows: int,
    device_accepted: bool | None = None,
) -> dict[str, Any]:
    """Construct an additive run-manifest dict.

    All reproducibility context lives here; ``version.json`` is never touched.
    ``gpu_info`` should be ``None`` when ``device == "cpu"``. ``cache_hit_rate``
    may be ``None`` until the cross-run feature cache is wired (Plan 18-05).
    ``device_accepted`` records the GPU equivalence-guard outcome (``None`` when
    no GPU comparison was performed).
    """
    stages = {str(k): float(v) for k, v in (wall_clock_stages or {}).items()}
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "phase": PHASE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed": int(seed),
        "timeframe": str(timeframe),
        "data_csv": str(data_csv_path) if data_csv_path is not None else None,
        "data_hash": _compute_data_hash(data_csv_path),
        "fetched_months": float(fetched_months),
        "n_windows": int(n_windows),
        "device": str(device),
        "gpu_info": gpu_info if device == "cuda" else None,
        "device_accepted": device_accepted,
        "wall_clock_seconds": {
            "total": round(sum(stages.values()), 6),
            "stages": stages,
        },
        "cache_hit_rate": (
            float(cache_hit_rate) if cache_hit_rate is not None else None
        ),
        "parallel_windows": int(parallel_windows),
        "git_sha": _compute_git_sha(),
        "pip_freeze_digest": _compute_pip_freeze_digest(),
        "python_version": platform.python_version(),
        "cpu": _cpu_info(),
    }
    return manifest


def write_run_manifest(manifest: dict[str, Any], version_dir: str | Path) -> str:
    """Write ``run_manifest.json`` into ``version_dir``; return the path.

    Uses an atomic write (temp file + ``os.replace``) so a partially-written
    manifest can never be read by downstream tooling.
    """
    import json

    target = Path(version_dir) / MANIFEST_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    return str(target)
