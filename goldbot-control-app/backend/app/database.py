"""Database connection and session helpers."""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.config import load_settings
from backend.app.models import Base

_SETTINGS = load_settings()
_SETTINGS.db_path.parent.mkdir(parents=True, exist_ok=True)

ENGINE = create_engine(
    f"sqlite:///{_SETTINGS.db_path}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=ENGINE, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables if they do not exist yet."""
    Base.metadata.create_all(bind=ENGINE)


@contextmanager
def get_session() -> Session:
    """Context-managed database session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

