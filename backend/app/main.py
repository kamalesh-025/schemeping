"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin,
    auth,
    chat,
    eligibility,
    events,
    facilities,
    family,
    features,
    health,
    notifications,
    privacy,
    profile,
    reference,
    schemes,
)
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.security import SecurityHeadersMiddleware

logger = get_logger(__name__)


def _init_sentry() -> None:
    """Initialise Sentry only when a DSN is configured. No-op otherwise."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
    )
    logger.info("sentry_initialised", extra={"environment": settings.sentry_environment})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "application_startup",
        extra={"app_env": settings.app_env, "version": app.version},
    )
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    _init_sentry()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "SchemePing API. Eligibility is decided by a deterministic rules engine; "
            "the LLM only explains verified scheme records."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-Request-ID"],
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(features.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(profile.router, prefix=settings.api_prefix)
    app.include_router(family.router, prefix=settings.api_prefix)
    app.include_router(eligibility.router, prefix=settings.api_prefix)
    app.include_router(schemes.router, prefix=settings.api_prefix)
    app.include_router(facilities.router, prefix=settings.api_prefix)
    app.include_router(notifications.router, prefix=settings.api_prefix)
    app.include_router(reference.router, prefix=settings.api_prefix)
    app.include_router(chat.router, prefix=settings.api_prefix)
    app.include_router(events.router, prefix=settings.api_prefix)
    app.include_router(privacy.router, prefix=settings.api_prefix)
    app.include_router(admin.router, prefix=settings.api_prefix)

    if settings.admin_panel_enabled:
        from app.admin_panel import mount_admin

        mount_admin(app)

    return app


app = create_app()
