"""OTP request / verification service.

Rules (AGENTS.md 10.1):
- OTP is stored only as an HMAC-SHA256 hash, never plaintext.
- 5 minute expiry.
- Max 3 requests per mobile per 15 minutes.
- Max 5 verification attempts per OTP, then the OTP is locked.
- IP-based request limiting as a second line of defence.

All comparisons use UTC-aware datetimes because MySQL drops the timezone on
``DATETIME`` columns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    generate_otp,
    hash_otp,
    mask_mobile,
    otp_matches,
)
from app.core.time import ensure_utc, utcnow
from app.models.otp import OtpRequest
from app.services.messaging import MessagingProvider, get_messaging_provider

SMS_SENT_MESSAGE = "If this number can receive SMS, an OTP has been sent."


class OtpError(Exception):
    """Base class for OTP failures that map to 4xx responses."""


class OtpRateLimited(OtpError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many OTP requests. Please wait before trying again.")
        self.retry_after_seconds = retry_after_seconds


class OtpInvalid(OtpError):
    pass


class OtpExpired(OtpError):
    pass


class OtpLocked(OtpError):
    pass


@dataclass(frozen=True)
class OtpRequestResult:
    expires_in_seconds: int
    resend_after_seconds: int


def _window_start() -> datetime:
    settings = get_settings()
    return utcnow() - timedelta(minutes=settings.otp_request_window_minutes)


def _count_recent(session: Session, *, mobile: str | None = None, ip: str | None = None) -> int:
    stmt = select(func.count(OtpRequest.id)).where(OtpRequest.created_at >= _window_start())
    if mobile is not None:
        stmt = stmt.where(OtpRequest.mobile == mobile)
    if ip is not None:
        stmt = stmt.where(OtpRequest.ip_address == ip)
    return int(session.scalar(stmt) or 0)


def _seconds_until_oldest_leaves_window(session: Session, mobile: str) -> int:
    settings = get_settings()
    oldest = session.scalar(
        select(func.min(OtpRequest.created_at)).where(
            OtpRequest.mobile == mobile, OtpRequest.created_at >= _window_start()
        )
    )
    oldest_utc = ensure_utc(oldest if isinstance(oldest, datetime) else None)
    if oldest_utc is None:
        return settings.otp_request_window_minutes * 60
    leaves_at = oldest_utc + timedelta(minutes=settings.otp_request_window_minutes)
    return max(int((leaves_at - utcnow()).total_seconds()), 1)


def request_otp(
    session: Session,
    mobile: str,
    *,
    ip_address: str | None,
    provider: MessagingProvider | None = None,
) -> OtpRequestResult:
    """Create and send an OTP, enforcing per-mobile and per-IP limits."""
    settings = get_settings()

    if _count_recent(session, mobile=mobile) >= settings.otp_max_requests_per_mobile:
        raise OtpRateLimited(_seconds_until_oldest_leaves_window(session, mobile))

    if ip_address and _count_recent(session, ip=ip_address) >= settings.otp_max_requests_per_ip:
        raise OtpRateLimited(settings.otp_request_window_minutes * 60)

    code = generate_otp(settings.otp_length)
    record = OtpRequest(
        mobile=mobile,
        otp_hash=hash_otp(mobile, code),
        expires_at=utcnow() + timedelta(minutes=settings.otp_ttl_minutes),
        attempts=0,
        ip_address=ip_address,
    )
    session.add(record)
    session.flush()

    (provider or get_messaging_provider()).send_otp(mobile, code)
    session.commit()

    return OtpRequestResult(
        expires_in_seconds=settings.otp_ttl_minutes * 60,
        resend_after_seconds=60,
    )


def verify_otp(session: Session, mobile: str, code: str) -> None:
    """Consume the newest OTP for ``mobile`` or raise an ``OtpError``."""
    settings = get_settings()
    record = session.scalars(
        select(OtpRequest)
        .where(OtpRequest.mobile == mobile, OtpRequest.consumed_at.is_(None))
        .order_by(OtpRequest.created_at.desc(), OtpRequest.id.desc())
        .limit(1)
    ).first()

    if record is None:
        raise OtpInvalid("Request a new OTP.")

    if record.attempts >= settings.otp_max_attempts:
        raise OtpLocked("Too many wrong attempts. Request a new OTP.")

    expires_at = ensure_utc(record.expires_at)
    if expires_at is None or expires_at <= utcnow():
        raise OtpExpired("This OTP has expired. Request a new one.")

    if not otp_matches(mobile, code, record.otp_hash):
        record.attempts += 1
        session.commit()
        remaining = settings.otp_max_attempts - record.attempts
        if remaining <= 0:
            # The record stays unconsumed so the next attempt is refused as
            # "locked" rather than reported as a generic bad request.
            raise OtpInvalid("Too many wrong attempts. Request a new OTP.")
        raise OtpInvalid(
            f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} left."
        )

    record.consumed_at = utcnow()
    # Any older unconsumed OTPs for this mobile become invalid too.
    for stale in session.scalars(
        select(OtpRequest).where(
            OtpRequest.mobile == mobile,
            OtpRequest.consumed_at.is_(None),
            OtpRequest.id != record.id,
        )
    ):
        stale.consumed_at = utcnow()
    session.commit()


def purge_expired(session: Session, older_than_days: int = 7) -> int:
    """Delete old OTP rows. Called by a maintenance job, not on the hot path."""
    cutoff = utcnow() - timedelta(days=older_than_days)
    deleted = session.query(OtpRequest).filter(OtpRequest.created_at < cutoff).delete()
    session.commit()
    return int(deleted)


def describe_for_log(mobile: str) -> str:
    return mask_mobile(mobile)
