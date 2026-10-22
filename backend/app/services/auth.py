"""Session issuance and rotation.

Access tokens are stateless JWTs. Refresh tokens are opaque, hashed at rest,
and rotated on every refresh. Presenting an already-rotated token is treated as
theft: the entire token family is revoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    TokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.core.time import ensure_utc, utcnow
from app.models.enums import Language
from app.models.refresh_token import RefreshToken
from app.models.user import User


class SessionError(Exception):
    """Raised when a refresh token cannot be used."""


class AccountExists(Exception):
    """Registration was attempted for a mobile number that already has an account."""


class InvalidCredentials(Exception):
    """The mobile number or password is wrong, or the account has no password."""


@dataclass(frozen=True)
class IssuedSession:
    access_token: str
    refresh_token: str
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


@dataclass(frozen=True)
class RotatedSession:
    session: IssuedSession
    user: User


def _issue(
    session: Session,
    user_id: int,
    *,
    family_id: str,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    settings = get_settings()
    refresh_token = generate_refresh_token()
    refresh_expires = timedelta(days=settings.refresh_token_ttl_days)

    session.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(refresh_token),
            family_id=family_id,
            expires_at=utcnow() + refresh_expires,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:255] or None,
        )
    )

    return IssuedSession(
        access_token=create_access_token(user_id),
        refresh_token=refresh_token,
        access_expires_in_seconds=settings.access_token_ttl_minutes * 60,
        refresh_expires_in_seconds=int(refresh_expires.total_seconds()),
    )


def start_session(
    session: Session,
    user: User,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> IssuedSession:
    """Log a user in: a brand-new refresh-token family."""
    issued = _issue(
        session,
        user.id,
        family_id=generate_refresh_token()[:32],
        ip_address=ip_address,
        user_agent=user_agent,
    )
    user.last_login_at = utcnow()
    session.commit()
    return issued


def rotate_session(
    session: Session,
    refresh_token: str,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> RotatedSession:
    token_hash = hash_refresh_token(refresh_token)
    stored = session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )

    if stored is None:
        raise SessionError("Session expired. Please log in again.")

    if stored.revoked_at is not None:
        raise SessionError("Session revoked. Please log in again.")

    if stored.rotated_at is not None:
        # Replay of an already-used token: assume compromise.
        revoke_family(session, stored.family_id)
        raise SessionError("Session reused. Please log in again.")

    expires_at = ensure_utc(stored.expires_at)
    if expires_at is None or expires_at <= utcnow():
        stored.revoked_at = utcnow()
        session.commit()
        raise SessionError("Session expired. Please log in again.")

    user = session.get(User, stored.user_id)
    if user is None or user.deleted_at is not None:
        stored.revoked_at = utcnow()
        session.commit()
        raise SessionError("Account no longer exists.")

    stored.rotated_at = utcnow()
    issued = _issue(
        session,
        user.id,
        family_id=stored.family_id,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.commit()
    return RotatedSession(session=issued, user=user)


def revoke_token(session: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    stored = session.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == hash_refresh_token(refresh_token)
        )
    )
    if stored is not None and stored.revoked_at is None:
        stored.revoked_at = utcnow()
        session.commit()


def revoke_all_for_user(session: Session, user_id: int) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def revoke_other_sessions(
    session: Session, user_id: int, keep_refresh_token: str | None
) -> None:
    """Revoke every live session except the caller's (used on password change)."""
    statement = update(RefreshToken).where(
        RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
    )
    if keep_refresh_token:
        statement = statement.where(
            RefreshToken.token_hash != hash_refresh_token(keep_refresh_token)
        )
    session.execute(statement.values(revoked_at=utcnow()))


def revoke_family(session: Session, family_id: str) -> None:
    session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    session.commit()


def user_from_access_token(session: Session, token: str) -> User | None:
    try:
        user_id = decode_access_token(token)
    except TokenError:
        return None

    user = session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


# ------------------------------------------------------------------ passwords


def register_user(
    session: Session, *, mobile: str, password: str, name: str | None = None
) -> User:
    """Create an account for a mobile number, or raise ``AccountExists``.

    Registration is not a verification step: nothing proves the caller owns the
    number. ``mobile_verified_at`` stays NULL until an OTP flow proves it.
    """
    existing = session.scalar(select(User).where(User.mobile == mobile))
    if existing is not None:
        raise AccountExists("An account already exists for this number.")

    user = User(
        mobile=mobile,
        name=name,
        password_hash=hash_password(password),
        language=Language.ENGLISH,
        consent_data_processing=False,
        consent_whatsapp=False,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, *, mobile: str, password: str) -> User:
    """Return the user for correct credentials, or raise ``InvalidCredentials``.

    The same error is raised for an unknown number and a wrong password, and an
    unknown number still runs one password check so the response time does not
    reveal which accounts exist.
    """
    user = session.scalar(
        select(User).where(User.mobile == mobile, User.deleted_at.is_(None))
    )
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise InvalidCredentials("Mobile number or password is incorrect.")

    if not verify_password(password, user.password_hash):
        raise InvalidCredentials("Mobile number or password is incorrect.")

    if password_needs_rehash(user.password_hash):
        # Login is the only moment the plaintext is available, so upgrade weak
        # parameters here instead of forcing a reset.
        user.password_hash = hash_password(password)
        session.commit()

    return user


def change_password(session: Session, user: User, current: str, new: str) -> None:
    """Verify the current password and replace it. Caller revokes other sessions."""
    if not verify_password(current, user.password_hash):
        raise InvalidCredentials("Current password is incorrect.")
    user.password_hash = hash_password(new)
    session.commit()
