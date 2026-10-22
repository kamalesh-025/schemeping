"""Shared FastAPI dependencies: current user and cookie handling."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.user import User
from app.services.auth import user_from_access_token

DbSession = Annotated[Session, Depends(get_db)]


def _cookie_secure() -> bool:
    settings = get_settings()
    if settings.cookie_secure is not None:
        return settings.cookie_secure
    return settings.is_production


def set_session_cookies(
    response: Response, *, access_token: str, refresh_token: str
) -> None:
    """httpOnly cookies so JavaScript can never read the tokens."""
    settings = get_settings()
    domain = settings.cookie_domain or None
    secure = _cookie_secure()

    response.set_cookie(
        key=settings.access_cookie_name,
        value=access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
    )
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        domain=domain,
    )


def clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    for name in (settings.access_cookie_name, settings.refresh_cookie_name):
        response.delete_cookie(name, path="/")


def get_current_user(request: Request, db: DbSession) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        authorization = request.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Please log in to continue."
        )

    user = user_from_access_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Please log in again.",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
