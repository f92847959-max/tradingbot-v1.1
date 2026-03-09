"""Runtime configuration for the goldbot control app backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ControlAppSettings:
    """Settings loaded from environment variables with safe defaults."""

    project_root: Path
    db_path: Path
    source_db_path: Path
    api_host: str
    api_port: int
    retention_days: int
    access_token: str


def load_settings() -> ControlAppSettings:
    """Load settings from environment variables."""
    project_root = Path(__file__).resolve().parents[2]
    db_path = Path(
        os.getenv("CONTROL_APP_DB_PATH", str(project_root / "database" / "control_app.db"))
    )
    source_db_path = Path(
        os.getenv(
            "CONTROL_APP_SOURCE_DB_PATH",
            str(project_root.parent / "data" / "gold_trader.db"),
        )
    )
    api_host = os.getenv("CONTROL_APP_API_HOST", "127.0.0.1")
    api_port = int(os.getenv("CONTROL_APP_API_PORT", "8060"))
    retention_days = int(os.getenv("CONTROL_APP_RETENTION_DAYS", "30"))
    access_token = os.getenv("CONTROL_APP_ACCESS_TOKEN", "1")
    return ControlAppSettings(
        project_root=project_root,
        db_path=db_path,
        source_db_path=source_db_path,
        api_host=api_host,
        api_port=api_port,
        retention_days=retention_days,
        access_token=access_token,
    )
