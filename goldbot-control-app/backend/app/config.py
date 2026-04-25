"""Runtime configuration for the goldbot control app backend."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Placeholder tokens that must never be accepted as a real access token.
_PLACEHOLDER_TOKENS = frozenset(
    {
        "bitte-token-setzen",
        "bitte-eigenen-token-setzen",
    }
)


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

    raw_port = os.getenv("CONTROL_APP_API_PORT", "8060")
    try:
        api_port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"CONTROL_APP_API_PORT must be an integer, got: {raw_port!r}"
        ) from exc
    if not (1024 <= api_port <= 65535):
        raise ValueError(
            f"CONTROL_APP_API_PORT must be in range 1024-65535, got: {api_port}"
        )

    retention_days = int(os.getenv("CONTROL_APP_RETENTION_DAYS", "30"))

    access_token = os.getenv("CONTROL_APP_ACCESS_TOKEN", "").strip()
    if access_token in _PLACEHOLDER_TOKENS:
        raise RuntimeError("Control-App token not configured")

    return ControlAppSettings(
        project_root=project_root,
        db_path=db_path,
        source_db_path=source_db_path,
        api_host=api_host,
        api_port=api_port,
        retention_days=retention_days,
        access_token=access_token,
    )
