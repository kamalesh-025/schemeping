"""Celery tasks for proactive WhatsApp notifications (Phase 5).

Guarantees live in ``app.services.notifications.queue_notification``:
opt-in enforcement, category preferences, dedupe via a unique key, and
quiet hours (9 PM-8 AM IST). The tasks call it for every message; nothing
here sends directly.

Schedules (beat, IST):
- daily eligibility scan: 07:30
- deadline reminders: 10:00
"""

from __future__ import annotations

import random
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.time import age_on, utcnow
from app.models.eligibility import EligibilityResult
from app.models.enums import (
    EligibilityStatus,
    NotificationStatus,
    NotificationType,
    SchemeStatus,
)
from app.models.notification import Notification
from app.models.scheme import Scheme
from app.models.user import User
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

DEADLINE_OFFSETS: tuple[int, ...] = (7, 3, 1)

# Only these three UI languages have written lines; the rest fall back.
_MILESTONE_LINES: dict[str, dict[str, str]] = {
    "en": {
        "18": "{name} just turned 18.",
        "60": "{name} just turned 60 and now meets senior-age rules.",
    },
    "ta": {
        "18": "{name} தற்போது 18 வயதை அடைந்தார்.",
        "60": "{name} தற்போது 60 வயதை அடைந்தார்; மூத்த குடிமகன் விதிகள் பொருந்தும்.",
    },
    "hi": {
        "18": "{name} अभी 18 साल के हुए।",
        "60": "{name} अभी 60 साल के हुए; वरिष्ठ नागरिक नियम लागू होते हैं।",
    },
}


def _db_session() -> Session:
    """A fresh session per task; imported late so tests can monkeypatch."""
    from app.core.db import SessionLocal

    return SessionLocal()


def _language_value(user: User) -> str:
    return user.language.value if hasattr(user.language, "value") else str(user.language)


def _person_name(user: User, member_id: int | None, members: dict[int, Any]) -> str:
    if member_id is None:
        return user.name or "Your profile"
    member = members.get(member_id)
    if member is None:
        return "Your family member"
    return member.name or "Your family member"


def _milestone_line(user: User, member: Any | None) -> str | None:
    """A birthday-rule milestone text, or None when this is not a birthday."""
    if member is None or member.dob is None:
        return None
    language = _language_value(user)
    lines = _MILESTONE_LINES.get(language, _MILESTONE_LINES["en"])
    age = age_on(member.dob, utcnow().date())
    line = lines.get(str(age))
    if line is None:
        return None
    name = member.name or "You"
    return line.format(name=name)


def _scheme_benefit(scheme: Scheme) -> str:
    return scheme.benefit_amount or scheme.benefit_summary or scheme.name


def _deadline_line(scheme: Scheme) -> str:
    if scheme.deadline is None:
        return "No last date; open in SchemePing soon."
    return f"Apply before {scheme.deadline.isoformat()}."


def _days_left(days_remaining: int) -> str:
    return f"{days_remaining} day{'s' if days_remaining != 1 else ''} left"


def _festival_window(scheme: Scheme, today: date) -> str:
    if scheme.deadline is not None:
        return scheme.deadline.isoformat()
    return today.isoformat()


# ------------------------------------------------------------------ sending


@celery_app.task(
    name="app.workers.tasks.send_notification",
    bind=True,
    max_retries=3,
)
def send_notification(self: Any, notification_id: int) -> dict[str, Any]:
    """Send one queued notification with exponential backoff retries.

    Status flow: queued -> sent (+provider_message_id). ``delivered`` and
    ``failed`` are final states reached via the provider webhook or by
    exhausting retries here.
    """
    from app.core.config import get_settings
    from app.services.messaging import (
        MessagingError,
        get_template,
        get_whatsapp_provider,
    )
    from app.services.notifications import can_notify

    settings = get_settings()
    db = _db_session()
    try:
        row = db.get(Notification, notification_id)
        if row is None:
            return {"status": "missing"}
        if row.status in (NotificationStatus.SENT, NotificationStatus.DELIVERED):
            return {"status": "already_sent", "notification_id": row.id}
        if row.status is NotificationStatus.FAILED:
            return {"status": "already_failed", "notification_id": row.id}

        user = db.get(User, row.user_id)
        if user is None:
            row.status = NotificationStatus.FAILED
            row.error = "not_allowed:user_missing"
            db.commit()
            return {
                "status": "blocked",
                "reason": "user_missing",
                "notification_id": row.id,
            }

        blocking = can_notify(user)
        if blocking is not None:
            # Opt-in revoked while queued (or STOP replied): never send.
            row.status = NotificationStatus.FAILED
            row.error = f"not_allowed:{blocking}"
            db.commit()
            return {"status": "blocked", "reason": blocking, "notification_id": row.id}

        template = get_template(row.template_name)
        params = {
            key: value
            for key, value in (row.payload or {}).items()
            if key in template.variables and value is not None
        }
        mobile = user.mobile if user is not None else ""
        try:
            provider = get_whatsapp_provider()
            provider_message_id = provider.send_template(
                mobile,
                row.template_name,
                params,
                language=_language_value(user),
            )
        except MessagingError as exc:
            retries_done = self.request.retries
            if retries_done < settings.send_notification_retries:
                backoff = min(2**retries_done * 5, 120)
                backoff_jitter = backoff + random.uniform(0, backoff * 0.2)
                raise self.retry(exc=exc, countdown=round(backoff_jitter)) from exc
            row.status = NotificationStatus.FAILED
            row.error = str(exc)[:500]
            db.commit()
            return {"status": "failed", "reason": str(exc), "notification_id": row.id}

        row.status = NotificationStatus.SENT
        row.sent_at = utcnow()
        if provider_message_id:
            row.provider_message_id = provider_message_id
        db.commit()
        logger.info(
            "notification_sent",
            extra={"notification_id": row.id, "template": row.template_name},
        )
        return {"status": "sent", "notification_id": row.id}
    finally:
        db.close()


# ------------------------------------------------------------------ daily scan


@celery_app.task(name="app.workers.tasks.daily_eligibility_scan")
def daily_eligibility_scan() -> dict[str, Any]:
    """Recompute ages from DOB, re-run eligibility, notify what is new.

    The diff compares each eligibility row's status before and after the
    recompute. A run over an unchanged database queues nothing, so calling
    the task twice never duplicates notifications: the dedupe key includes
    the person, scheme, template and today's scan date.
    """
    from app.services.eligibility import recompute_user
    from app.services.notifications import can_notify, queue_notification

    today = utcnow().date()
    db = _db_session()
    scanned = notified = skipped = errors = 0
    try:
        users = db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.id)).all()
        for user in users:
            scanned += 1
            blocking = can_notify(user)
            if blocking is not None:
                skipped += 1
                continue

            before = {
                (result.family_member_id, result.scheme_id): str(result.status)
                for result in db.scalars(
                    select(EligibilityResult).where(EligibilityResult.user_id == user.id)
                ).all()
            }
            try:
                recompute_user(db, user)
            except Exception as exc:
                db.rollback()
                errors += 1
                logger.error("scan_recompute_failed user=%s error=%r", user.id, exc)
                continue

            members = {member.id: member for member in user.family_members}
            for result in db.scalars(
                select(EligibilityResult).where(EligibilityResult.user_id == user.id)
            ).all():
                if result.status is not EligibilityStatus.ELIGIBLE:
                    continue
                key = (result.family_member_id, result.scheme_id)
                if before.get(key) == str(result.status):
                    continue  # was already eligible: not news

                scheme = db.get(Scheme, result.scheme_id)
                if scheme is None:
                    continue
                member = (
                    members.get(result.family_member_id)
                    if result.family_member_id is not None
                    else None
                )
                milestone = (
                    _milestone_line(user, member) if result.family_member_id is not None else None
                )
                if milestone is not None:
                    # An age/status crossing (e.g. daughter turns 18).
                    template = "family_milestone"
                    params: dict[str, Any] = {
                        "person_name": _person_name(user, result.family_member_id, members),
                        "milestone_line": milestone,
                        "scheme_name": scheme.name,
                        "benefit": _scheme_benefit(scheme),
                    }
                else:
                    template = "new_scheme_eligible"
                    person_label = _person_name(user, result.family_member_id, members)
                    params = {
                        "person_name_line": (
                            "" if person_label is None else f": {person_label}"
                        ),
                        "scheme_name": scheme.name,
                        "benefit": _scheme_benefit(scheme),
                        "deadline_line": _deadline_line(scheme),
                    }
                person_label_db = (
                    result.family_member_id if result.family_member_id is not None else "me"
                )
                dedupe_key = (
                    f"{template}:scheme={scheme.id}:person={person_label_db}:"
                    f"scan={today.isoformat()}"
                )
                outcome = queue_notification(
                    db,
                    user,
                    notification_type=NotificationType.FAMILY_MILESTONE
                    if template == "family_milestone"
                    else NotificationType.NEW_SCHEME_ELIGIBLE,
                    template_name=template,
                    params=params,
                    dedupe_key=dedupe_key,
                )
                if outcome.queued:
                    notified += 1
        return {
            "scanned": scanned,
            "notified": notified,
            "skipped": skipped,
            "errors": errors,
            "scan_date": today.isoformat(),
        }
    finally:
        db.close()


# ------------------------------------------------------------------ deadlines


@celery_app.task(name="app.workers.tasks.deadline_reminders")
def deadline_reminders() -> dict[str, Any]:
    """Remind eligible users 7, 3 and 1 days before a deadline."""
    from app.services.notifications import can_notify, queue_notification

    today = utcnow().date()
    queued = 0
    schemes_seen = 0
    db = _db_session()
    try:
        schemes = db.scalars(
            select(Scheme)
            .where(Scheme.status == SchemeStatus.PUBLISHED)
            .where(Scheme.deadline.is_not(None))
            .order_by(Scheme.id)
        ).all()
        for scheme in schemes:
            deadline = scheme.deadline
            if deadline is None:  # the query filters, mypy needs the narrow
                continue
            days_remaining = (deadline - today).days
            if days_remaining not in DEADLINE_OFFSETS:
                continue
            schemes_seen += 1
            results = db.scalars(
                select(EligibilityResult).where(
                    EligibilityResult.scheme_id == scheme.id,
                    EligibilityResult.status == EligibilityStatus.ELIGIBLE,
                )
            ).all()
            for result in results:
                user = db.get(User, result.user_id)
                if user is None or can_notify(user) is not None:
                    continue
                person_label = (
                    result.family_member_id if result.family_member_id is not None else "me"
                )
                outcome = queue_notification(
                    db,
                    user,
                    notification_type=NotificationType.DEADLINE_REMINDER,
                    template_name="deadline_reminder",
                    params={
                        "scheme_name": scheme.name,
                        "job_name": person_label,
                        "days_left": _days_left(days_remaining),
                        "deadline_line": _deadline_line(scheme),
                    },
                    dedupe_key=(
                        f"deadline_reminder:scheme={scheme.id}:person={person_label}:"
                        f"window={deadline.isoformat()}:{days_remaining}d"
                    ),
                )
                if outcome.queued:
                    queued += 1
        return {"schemes": schemes_seen, "reminders": queued}
    finally:
        db.close()


# ------------------------------------------------------------------ broadcasts


@celery_app.task(name="app.workers.tasks.festival_benefit_broadcast")
def festival_benefit_broadcast(scheme_id: int) -> dict[str, Any]:
    """Tell opted-in, scheme-region users about a festival scheme."""
    from app.services.notifications import queue_notification
    from app.services.targeting import region_covers

    db = _db_session()
    queued = skipped = 0
    try:
        scheme = db.get(Scheme, scheme_id)
        if scheme is None or scheme.status is not SchemeStatus.PUBLISHED:
            return {"status": "not_published", "queued": 0}
        today = utcnow().date()
        users = db.scalars(
            select(User)
            .where(User.deleted_at.is_(None))
            .where(User.consent_whatsapp.is_(True))
            # Consent, not mobile verification, is the gate: password sign-in
            # never proves ownership of the number (see AGENTS.md 18.4).
            .where(User.whatsapp_opted_out_at.is_(None))
            .order_by(User.id)
        ).all()
        for user in users:
            if scheme.state is not None and not region_covers(
                [{"state": scheme.state}], user.state, user.district
            ):
                skipped += 1
                continue
            language = _language_value(user)
            greeting = {
                "en": "Warm festival greetings from SchemePing!",
                "ta": "SchemePing விடுக்கும் பண்டிகை நல்வாழ்த்துகள்!",
                "hi": "SchemePing की ओर से त्योहार की शुभकामनाएँ!",
            }.get(language, "Warm festival greetings from SchemePing!")
            outcome = queue_notification(
                db,
                user,
                notification_type=NotificationType.FESTIVAL_BENEFIT,
                template_name="festival_benefit",
                params={
                    "greeting": greeting,
                    "scheme_name": scheme.name,
                    "benefit": _scheme_benefit(scheme),
                    "deadline_line": _deadline_line(scheme),
                },
                dedupe_key=(
                    f"festival_benefit:scheme={scheme.id}:user={user.id}:"
                    f"window={_festival_window(scheme, today)}"
                ),
            )
            if outcome.queued:
                queued += 1
            else:
                skipped += 1
        return {"scheme_id": scheme_id, "queued": queued, "skipped": skipped}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.purge_chat_history")
def purge_chat_history() -> dict[str, Any]:
    """Delete chat transcripts older than the retention window (default 14 days)."""
    from datetime import timedelta

    from app.core.config import get_settings
    from app.models.chat import ChatMessage

    settings = get_settings()
    cutoff = utcnow() - timedelta(days=settings.chat_history_retention_days)
    db = _db_session()
    try:
        rows = db.scalars(
            select(ChatMessage).where(ChatMessage.created_at < cutoff)
        ).all()
        for row in rows:
            db.delete(row)
        db.commit()
        logger.info("chat_history_purged", extra={"deleted": len(rows)})
        return {"deleted": len(rows), "cutoff": cutoff.isoformat()}
    finally:
        db.close()
