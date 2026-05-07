"""
Model Versioning -- Versioned model directory management.

Provides utilities for creating versioned model directories, writing
version metadata (version.json), maintaining a production pointer
(production.json), and cleaning up old versions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

logger = logging.getLogger(__name__)


SPECIALIST_ROOT_DIR = "specialists"


def _sanitize_artifact_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name.strip())
    return cleaned.strip("_") or "specialist"


def create_version_dir(base_dir: str) -> str:
    """Create a new versioned model directory.

    Format: v{NNN}_{YYYYMMDD}_{HHMMSS} (e.g., v001_20260306_143022).
    Scans existing v* directories to determine next version number.

    Args:
        base_dir: Base directory for saved models.

    Returns:
        Full path to the newly created version directory.
    """
    os.makedirs(base_dir, exist_ok=True)
    existing = [
        d
        for d in os.listdir(base_dir)
        if os.path.isdir(os.path.join(base_dir, d)) and d.startswith("v")
    ]

    if existing:
        max_num = 0
        for d in existing:
            match = re.match(r"v(\d+)", d)
            if match:
                max_num = max(max_num, int(match.group(1)))
        next_num = max_num + 1
    else:
        next_num = 1

    while True:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        version_name = f"v{next_num:03d}_{timestamp}"
        version_dir = os.path.join(base_dir, version_name)
        try:
            os.makedirs(version_dir, exist_ok=False)
            break
        except FileExistsError:
            next_num += 1

    logger.info(f"Created version directory: {version_name}")
    return version_dir


def _atomic_write_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def _atomic_copy(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) if os.path.dirname(dst) else ".", exist_ok=True)
    tmp = f"{dst}.tmp.{os.getpid()}"
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def write_version_json(version_dir: str, version_data: dict) -> str:
    """Write version.json to a version directory.

    The version_data dict should contain all fields from the existing
    model_metadata.json format plus the new walk-forward and versioning
    fields.

    Args:
        version_dir: Path to the version directory.
        version_data: Dictionary of version metadata.

    Returns:
        Full path to the written version.json file.
    """
    version_path = os.path.join(version_dir, "version.json")
    _atomic_write_json(version_path, version_data)

    logger.info(f"Wrote version.json to {os.path.basename(version_dir)}")
    return version_path


def update_production_pointer(base_dir: str, version_dir: str) -> None:
    """Update the production pointer to a new version.

    Writes production.json to base_dir, copies model files and governance
    artifacts from version_dir to base_dir for backward compatibility, and
    copies version.json as model_metadata.json.

    Args:
        base_dir: Base directory for saved models.
        version_dir: Path to the version directory to promote.
    """
    # Copy model files to base dir for backward compatibility before
    # publishing the pointer. Missing files clear stale flat copies.
    model_files = [
        "xgboost_gold.pkl",
        "lightgbm_gold.pkl",
        "feature_scaler.pkl",
        "xgboost_calibrator.pkl",
        "lightgbm_calibrator.pkl",
        "calibration.json",
        "thresholds.json",
    ]
    for filename in model_files:
        src = os.path.join(version_dir, filename)
        dst = os.path.join(base_dir, filename)
        if os.path.exists(src):
            _atomic_copy(src, dst)
            logger.info(f"  Copied {filename} to base directory")
        elif os.path.exists(dst):
            os.remove(dst)
            logger.info(f"  Removed stale {filename} from base directory")

    # Copy version.json as model_metadata.json for backward compatibility
    version_json_src = os.path.join(version_dir, "version.json")
    metadata_dst = os.path.join(base_dir, "model_metadata.json")
    if os.path.exists(version_json_src):
        _atomic_copy(version_json_src, metadata_dst)
        logger.info("  Copied version.json as model_metadata.json")

    pointer_path = os.path.join(base_dir, "production.json")
    pointer = {
        "version_dir": os.path.basename(version_dir),
        "updated": datetime.now(timezone.utc).isoformat(),
        "path": os.path.abspath(version_dir),
    }
    _atomic_write_json(pointer_path, pointer)

    logger.info(
        f"Production pointer updated to {os.path.basename(version_dir)}"
    )


def cleanup_old_versions(base_dir: str, keep: int = 5) -> List[str]:
    """Delete old version directories beyond the retention limit.

    Lists all v* directories, sorts by version number, and deletes
    directories beyond the `keep` most recent.

    Args:
        base_dir: Base directory for saved models.
        keep: Number of most recent versions to keep.

    Returns:
        List of deleted directory names.
    """
    existing = []
    for d in os.listdir(base_dir):
        full_path = os.path.join(base_dir, d)
        if os.path.isdir(full_path) and d.startswith("v"):
            match = re.match(r"v(\d+)", d)
            if match:
                existing.append((int(match.group(1)), d))

    # Sort by version number ascending
    existing.sort(key=lambda x: x[0])

    deleted: List[str] = []
    if len(existing) > keep:
        to_delete = existing[: len(existing) - keep]
        for _num, dirname in to_delete:
            dir_path = os.path.join(base_dir, dirname)
            shutil.rmtree(dir_path)
            deleted.append(dirname)
            logger.info(f"Deleted old version: {dirname}")

    if deleted:
        logger.info(f"Cleaned up {len(deleted)} old version(s)")
    else:
        logger.debug("No old versions to clean up")

    return deleted


def get_specialist_root(base_dir: str, specialist_name: str) -> str:
    """Return the isolated artifact root for a specialist model."""
    slug = _sanitize_artifact_name(specialist_name)
    return os.path.join(base_dir, SPECIALIST_ROOT_DIR, slug)


def resolve_version_dir_from_pointer(root_dir: str, pointer: dict) -> str:
    """Resolve and validate a production pointer inside an artifact root."""
    version_name = str(pointer.get("version_dir", "")).strip()
    if not version_name:
        raise ValueError("production pointer missing version_dir")
    raw_path = pointer.get("path")
    candidate = str(raw_path) if raw_path else os.path.join(root_dir, version_name)
    root_abs = os.path.abspath(root_dir)
    candidate_abs = os.path.abspath(candidate)
    try:
        common = os.path.commonpath([root_abs, candidate_abs])
    except ValueError as exc:
        raise ValueError("production pointer path is outside artifact root") from exc
    if common != root_abs:
        raise ValueError("production pointer path is outside artifact root")
    if version_name and os.path.basename(candidate_abs) != version_name:
        raise ValueError("production pointer path does not match version_dir")
    return candidate_abs


def create_specialist_version_dir(base_dir: str, specialist_name: str) -> str:
    """Create a specialist-only version directory under the isolated root."""
    specialist_root = get_specialist_root(base_dir, specialist_name)
    os.makedirs(specialist_root, exist_ok=True)
    return create_version_dir(specialist_root)


def update_specialist_production_pointer(
    base_dir: str,
    specialist_name: str,
    version_dir: str,
    artifact_files: Iterable[str] | None = None,
) -> str:
    """Promote a specialist version without touching the core model root."""
    specialist_root = get_specialist_root(base_dir, specialist_name)
    os.makedirs(specialist_root, exist_ok=True)

    files_to_copy = list(artifact_files or [])
    if not files_to_copy:
        files_to_copy = [
            "specialist_lightgbm.pkl",
            "specialist_scaler.pkl",
            "specialist_version.json",
            "feature_block.json",
            "version.json",
        ]

    for filename in files_to_copy:
        src = os.path.join(version_dir, filename)
        dst = os.path.join(specialist_root, os.path.basename(filename))
        if os.path.exists(src):
            _atomic_copy(src, dst)
            logger.info("  Copied specialist artifact %s", os.path.basename(filename))
        elif os.path.exists(dst):
            os.remove(dst)
            logger.info("  Removed stale specialist artifact %s", os.path.basename(filename))

    version_json_src = os.path.join(version_dir, "version.json")
    metadata_dst = os.path.join(specialist_root, "specialist_model_metadata.json")
    if os.path.exists(version_json_src):
        _atomic_copy(version_json_src, metadata_dst)
        logger.info("  Copied version.json as specialist_model_metadata.json")

    pointer_path = os.path.join(specialist_root, "production.json")
    pointer = {
        "specialist_name": specialist_name,
        "version_dir": os.path.basename(version_dir),
        "updated": datetime.now(timezone.utc).isoformat(),
        "path": os.path.abspath(version_dir),
    }
    _atomic_write_json(pointer_path, pointer)

    logger.info(
        "Specialist production pointer updated: %s -> %s",
        specialist_name,
        os.path.basename(version_dir),
    )

    return pointer_path
