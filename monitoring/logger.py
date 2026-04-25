"""Centralised logging setup for the Gold Intraday Trading System.

Usage:
    from monitoring.logger import setup_logging, get_logger
    setup_logging()
    logger = get_logger(__name__)
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_configured = False
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_DIR = "logs"
LOG_FILE = "logs/trading.log"
MAX_BYTES = 50 * 1024 * 1024  # 50 MB
BACKUP_COUNT = 5


def setup_logging(level: str | None = None) -> None:
    """Configure root logger with console + rotating file handler.

    Safe to call multiple times — only configures once.
    """
    global _configured
    if _configured:
        return

    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()

    os.makedirs(LOG_DIR, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers (avoids duplicates when reimporting)
    root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

    # Console
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Rotating file
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Quieten noisy third-party libraries
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _configured = True
    logging.getLogger(__name__).info(
        "Logging configured: level=%s, file=%s", level, LOG_FILE
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call setup_logging() first."""
    return logging.getLogger(name)
