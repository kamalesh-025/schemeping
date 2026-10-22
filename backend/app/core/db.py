"""SQLAlchemy engine, session factory, and FastAPI dependency."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.database_echo,
    pool_pre_ping=True,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_recycle=settings.database_pool_recycle,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> tuple[bool, str | None]:
    """Return (healthy, error_message). Used by /health."""
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def session_scope() -> Any:
    """Context manager for use outside request handlers (workers, scripts)."""
    return SessionLocal()
