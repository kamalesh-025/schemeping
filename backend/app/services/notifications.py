"""Notification queueing and safety rules (Phase 5).

Every business-initiated WhatsApp message funnels through
``queue_notification`` so the guarantees hold in one place:

1. **Opt-in enforcement** — nothing is queued without
   ``consent_whatsapp=True`` and a verified mobile number.
2. **Category preferences** — each proactive category can be switched off
   by the user (Settings); ``scheme_summary`` is user-initiated and only
   needs the opt-in itself.
3. **Deduplication** — an optional ``dedupe_key`` hits a unique index
   (``notifications.dedupe_key``), so the same template for the same
   scheme/person/window can never be queued twice.
4. **Quiet hours** — non-urgent messages queued between 9 PM and 8 AM IST
   are released at the next 8 AM IST.
5. **Rate limiting** — the user-initiated endpoint is capped per hour.

Sending itself happens in ``app.workers.tasks.send_notification``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import quiet_hours_delay, utcnow
from app.models.enums import NotificationStatus, NotificationType
from app.models.notification import Notification
from app.models.user import User
from app.services.messaging import get_template
from app.services.notification_prefs import category_enabled

logger = get_logger(__name__)

NEEDS_OPT_IN = "needs_opt_in"


def user_language(user: User) -> str:
    """The user's language as a plain code, whatever the column stores."""
    return user.language.value if hasattr(user.language, "value") else str(user.language)


@dataclass(frozen=True)
class QueueOutcome:
    notification: Notification | None
    skipped: str | None = None

    @property
    def queued(self) -> bool:
        return self.notification is not None


def can_notify(user: User) -> str | None:
    """Why a user must not receive business-initiated messages, or None."""
    if not user.consent_whatsapp:
        return "not_opted_in"
    if user.mobile_verified_at is None:
        return "mobile_unverified"
    return None


def can_send_on_request(user: User) -> str | None:
    """Why a user must not receive a message they asked for, or None.

    A scheme summary is triggered by the user tapping the button, so the number
    does not need to be proven by an OTP: the account holder typed it and the
    consent is explicit. Business-initiated templates still go through
    ``can_notify`` because nothing on our side proves ownership of the number.
    """
    if not user.consent_whatsapp:
        return "not_opted_in"
    return None


def _schedule_send(notification: Notification, delay: timedelta | None) -> None:
    """Enqueue the drain task; import inline so tests can monkeypatch Celery."""
    from app.workers.tasks import send_notification

    if delay is not None and delay.total_seconds() > 0:
        send_notification.apply_async(
            args=[notification.id], countdown=round(delay.total_seconds())
        )
    else:
        send_notification.apply_async(args=[notification.id])


def queue_notification(
    db: Session,
    user: User,
    *,
    notification_type: NotificationType,
    template_name: str,
    params: dict[str, Any],
    dedupe_key: str | None = None,
    urgent: bool = False,
    skip_prefs: bool = False,
    on_request: bool = False,
) -> QueueOutcome:
    """Create one queued notification and schedule its send.

    Returns a ``QueueOutcome``; ``skipped`` explains why nothing was queued
    (never raises for user-state reasons). Provider/template errors still
    raise because they are programming errors, not user choices.

    ``on_request`` marks messages the user asked for (the WhatsApp button),
    which do not require a verified mobile number.
    """
    template = get_template(template_name)

    blocking = can_send_on_request(user) if on_request else can_notify(user)
    if blocking is not None:
        logger.info(
            "notification_skipped",
            extra={"user_id": user.id, "template": template_name, "reason": blocking},
        )
        return QueueOutcome(None, skipped=blocking)

    if (
        not skip_prefs
        and template.pref_category is not None
        and not category_enabled(user.notification_prefs, template.pref_category)
    ):
        logger.info(
            "notification_skipped",
            extra={"user_id": user.id, "template": template_name, "reason": "category_off"},
        )
        return QueueOutcome(None, skipped="category_off")

    delay = None if urgent else quiet_hours_delay()
    send_after = (utcnow() + delay) if delay else None

    notification = Notification(
        user_id=user.id,
        type=notification_type,
        template_name=template_name,
        payload=dict(params),
        status=NotificationStatus.QUEUED,
        dedupe_key=dedupe_key,
    )
    if send_after is not None:
        notification.payload["send_after"] = send_after.isoformat()
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        # The unique dedupe key raced or already exists: not a duplicate send.
        db.rollback()
        logger.info(
            "notification_deduped",
            extra={"user_id": user.id, "template": template_name, "key": dedupe_key},
        )
        return QueueOutcome(None, skipped="duplicate")

    _schedule_send(notification, delay)
    db.refresh(notification)
    return QueueOutcome(notification)


def send_whatsapp_rate_limited(db: Session, user_id: int) -> bool:
    """True when the hourly cap for user-initiated summaries is exhausted."""
    settings = get_settings()
    one_hour_ago = utcnow() - timedelta(hours=1)
    count = db.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user_id,
            Notification.type == NotificationType.SCHEME_SUMMARY,
            Notification.created_at >= one_hour_ago,
        )
    )
    return (count or 0) >= settings.send_whatsapp_hourly_limit


def build_scheme_summary_params(
    db: Session, user: User, scheme_id: int, *, language: str, person: str | int = "me"
) -> tuple[bool, dict[str, str] | str]:
    """Build the approved ``scheme_summary`` template parameters.

    Returns ``(ok, params_or_error)``; the error is a human-readable string
    for a 4xx response. Uses cached LLM translations for the citizen text,
    the deterministic engine facts for the eligibility line, and the nearest
    facility by district/pincode (no geolocation needed server-side).
    """
    from app.services import schemes as schemes_service
    from app.services.messaging import closing_line
    from app.services.schemes import PersonNotFoundError, SchemeNotFoundError

    try:
        payload = schemes_service.build_detail(
            db, user, schemes_service.load_published_scheme(db, scheme_id),
            language=language, person=person,
        )
    except SchemeNotFoundError:
        return False, "Scheme not found"
    except PersonNotFoundError:
        return False, "Person not found"

    translation = payload.get("translation") or {}
    fallback = translation.get("fallback", False)
    title = (
        translation.get("simple_title") or payload["name"]
        if not fallback
        else payload["name"]
    )
    benefits = translation.get("simple_benefits") or []
    benefit: str = (
        benefits[0]
        if not fallback and benefits
        else str(payload.get("benefit_amount") or payload.get("benefit_summary") or "-")
    )
    why = payload.get("why_qualify") or []
    eligibility_line = why[0] if why else "Open SchemePing to see the current status."
    documents = "; ".join(
        doc["name"] for doc in payload.get("required_documents", [])[:6]
    )
    deadline_value = payload.get("deadline")
    days_remaining = payload.get("days_remaining")
    if deadline_value is None:
        deadline = "No last date"
    elif isinstance(days_remaining, int) and days_remaining < 0:
        deadline = f"{deadline_value} (last date passed)"
    else:
        deadline = str(deadline_value)

    facility_name: str | None = None
    facilities = _nearest_facility_name(db, user)
    if facilities:
        facility_name = facilities

    params: dict[str, str] = {
        "scheme_name": title,
        "benefit": benefit,
        "eligibility_line": eligibility_line,
        "documents": documents or "-",
        "deadline": deadline,
        "facility_name": facility_name or "-",
        "closing_line": closing_line(language),
    }
    return True, params


def _nearest_facility_name(db: Session, user: User) -> str | None:
    from app.services.facilities import locate_facilities

    rows = locate_facilities(db, district=user.district, pincode=user.pincode, limit=1)
    return rows[0]["name"] if rows else None


def summary_dedupe_key(scheme_id: int, person: str | int, now: Any) -> str:
    """A short window (3 minutes) so accidental double taps cannot double-send."""
    window = int(now.timestamp() // 180)
    return f"scheme_summary:scheme={scheme_id}:person={person}:window={window}"


def render_summary_text(
    *,
    title: str,
    benefit: str,
    eligibility_line: str,
    documents: str,
    deadline: str,
    facility_name: str | None,
    language_line: str,
) -> str:
    """The scheme_summary template, rendered for the log/mock providers."""
    parts = [
        f"Scheme: {title}",
        f"Benefit: {benefit}",
        f"Eligibility: {eligibility_line}",
        f"Documents Needed: {documents}",
        f"Apply Before: {deadline}",
        f"Nearest Center: {facility_name or '-'}",
        language_line,
    ]
    return "\n".join(parts)
