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
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def create_version_dir(base_dir: str) -> str:
    """Create a new versioned model directory.

    Format: v{NNN}_{YYYYMMDD}_{HHMMSS} (e.g., v001_20260306_143022).
    Scans existing v* directories to determine next version number.

    Args:
        base_dir: Base directory for saved models.

    Returns:
        Full path to the newly created version directory.
    """
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    version_name = f"v{next_num:03d}_{timestamp}"
    version_dir = os.path.join(base_dir, version_name)
    os.makedirs(version_dir, exist_ok=True)

    logger.info(f"Created version directory: {version_name}")
    return version_dir


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
    with open(version_path, "w", encoding="utf-8") as f:
        json.dump(version_data, f, indent=2, ensure_ascii=False)

    logger.info(f"Wrote version.json to {os.path.basename(version_dir)}")
    return version_path


def update_production_pointer(base_dir: str, version_dir: str) -> None:
    """Update the production pointer to a new version.

    Writes production.json to base_dir, copies model files (xgboost_gold.pkl,
    lightgbm_gold.pkl, feature_scaler.pkl) from version_dir to base_dir for
    backward compatibility, and copies version.json as model_metadata.json.

    Args:
        base_dir: Base directory for saved models.
        version_dir: Path to the version directory to promote.
    """
    # Write production.json pointer
    pointer_path = os.path.join(base_dir, "production.json")
    pointer = {
        "version_dir": os.path.basename(version_dir),
        "updated": datetime.now().isoformat(),
        "path": version_dir,
    }
    with open(pointer_path, "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)

    logger.info(
        f"Production pointer updated to {os.path.basename(version_dir)}"
    )

    # Copy model files to base dir for backward compatibility
    model_files = ["xgboost_gold.pkl", "lightgbm_gold.pkl", "feature_scaler.pkl"]
    for filename in model_files:
        src = os.path.join(version_dir, filename)
        dst = os.path.join(base_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            logger.info(f"  Copied {filename} to base directory")

    # Copy version.json as model_metadata.json for backward compatibility
    version_json_src = os.path.join(version_dir, "version.json")
    metadata_dst = os.path.join(base_dir, "model_metadata.json")
    if os.path.exists(version_json_src):
        shutil.copy2(version_json_src, metadata_dst)
        logger.info("  Copied version.json as model_metadata.json")


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
