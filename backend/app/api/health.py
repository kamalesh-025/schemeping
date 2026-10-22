"""Health endpoints. Mounted at the root (not under the API prefix)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import check_database
from app.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    version: str
    environment: str
    detail: str | None = None


@router.get("/health", response_model=HealthResponse, summary="Liveness and DB readiness")
def health() -> HealthResponse:
    settings = get_settings()
    database_ok, error = check_database()

    if not database_ok:
        logger.warning("health_database_error", extra={"error": error})
        return HealthResponse(
            status="degraded",
            database="error",
            version="0.1.0",
            environment=settings.app_env,
            detail=error,
        )

    return HealthResponse(
        status="ok",
        database="ok",
        version="0.1.0",
        environment=settings.app_env,
    )


class ReadyResponse(BaseModel):
    ready: bool
    database: Literal["ok", "error"]
    detail: str | None = None


@router.get("/ready", response_model=ReadyResponse, summary="Readiness for load balancers")
def ready() -> ReadyResponse:
    """Ready means: the process answers AND the database is reachable."""
    database_ok, error = check_database()
    return ReadyResponse(
        ready=database_ok,
        database="ok" if database_ok else "error",
        detail=error,
    )
