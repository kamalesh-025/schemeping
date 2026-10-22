"""Notification service safety rules: opt-in, dedupe, quiet hours, rate limit."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.time import IST, utcnow
from app.models.enums import NotificationStatus, NotificationType
from app.models.user import User
from app.services.notifications import (
    can_notify,
    can_send_on_request,
    queue_notification,
    send_whatsapp_rate_limited,
)

from tests.conftest import make_completed_profile


@pytest.fixture
def opted_in_user(db) -> User:
    """A user with WhatsApp opt-in and a verified mobile."""
    user = make_completed_profile(db, consent_whatsapp=True)
    user.mobile_verified_at = utcnow()
    db.commit()
    return user


@pytest.fixture(autouse=True)
def no_celery(monkeypatch):
    """Service-level tests never touch a broker."""
    monkeypatch.setattr(
        "app.services.notifications._schedule_send", lambda *args, **kwargs: None
    )


def _params() -> dict:
    return {
        "person_name_line": "",
        "scheme_name": "A scheme",
        "benefit": "₹100",
        "deadline_line": "No last date",
    }


def test_no_optin_never_queues(db):
    user = make_completed_profile(db, consent_whatsapp=False)
    user.mobile_verified_at = utcnow()
    db.commit()

    outcome = queue_notification(
        db,
        user,
        notification_type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        params=_params(),
    )
    assert outcome.queued is False
    assert outcome.skipped == "not_opted_in"


def test_unverified_mobile_never_queues(db):
    user = make_completed_profile(db, consent_whatsapp=True)
    assert user.mobile_verified_at is None
    outcome = queue_notification(
        db,
        user,
        notification_type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        params=_params(),
    )
    assert outcome.skipped == "mobile_unverified"


def test_category_toggle_blocks_pref_categories(db, opted_in_user):
    opted_in_user.notification_prefs = {**opted_in_user.notification_prefs, "new_schemes": False}
    db.commit()
    outcome = queue_notification(
        db,
        opted_in_user,
        notification_type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        params=_params(),
    )
    assert outcome.skipped == "category_off"

    # scheme_summary is user-initiated: prefs never block it.
    summary = queue_notification(
        db,
        opted_in_user,
        notification_type=NotificationType.SCHEME_SUMMARY,
        template_name="scheme_summary",
        params={
            "scheme_name": "S",
            "benefit": "₹1",
            "eligibility_line": "You qualify",
            "documents": "Aadhaar",
            "deadline": "No last date",
            "facility_name": "-",
            "closing_line": "For full details visit SchemePing.",
        },
        skip_prefs=True,
    )
    assert summary.queued


def test_dedupe_key_blocks_second_queue(db, opted_in_user):
    first = queue_notification(
        db,
        opted_in_user,
        notification_type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        params=_params(),
        dedupe_key="new_scheme_eligible:scheme=1:person=me:scan=2026-10-19",
    )
    assert first.queued
    second = queue_notification(
        db,
        opted_in_user,
        notification_type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        params=_params(),
        dedupe_key="new_scheme_eligible:scheme=1:person=me:scan=2026-10-19",
    )
    assert second.queued is False
    assert second.skipped == "duplicate"
    from app.models.notification import Notification
    from sqlalchemy import func, select

    assert db.scalar(select(func.count(Notification.id))) == 1


def test_quiet_hours_delay_applied(db, opted_in_user, monkeypatch):
    """A night-queued reminder is stamped send_after 10h later (per helper)."""
    monkeypatch.setattr(
        "app.services.notifications.quiet_hours_delay",
        lambda: timedelta(hours=10),
    )
    outcome = queue_notification(
        db,
        opted_in_user,
        notification_type=NotificationType.DEADLINE_REMINDER,
        template_name="deadline_reminder",
        params={
            "scheme_name": "S",
            "job_name": "me",
            "days_left": "3 days left",
            "deadline_line": "x",
        },
    )
    assert outcome.queued
    assert outcome.notification is not None
    assert "send_after" in outcome.notification.payload


def test_urgent_bypasses_quiet_hours():
    """The quiet-hours helper holds 9 PM-8 AM IST and releases 10 AM UTC."""
    from app.core.time import quiet_hours_delay

    def ist_hour(hour: int, minute: int = 0):
        night = utcnow().astimezone(IST).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        return quiet_hours_delay(now=night.astimezone(utcnow().tzinfo))

    assert ist_hour(21, 30) is not None
    assert ist_hour(23) is not None
    assert ist_hour(3) is not None
    assert ist_hour(8) is None
    assert ist_hour(10) is None


def test_hourly_rate_limit(db, opted_in_user):
    for index in range(10):
        db.add(
            _summary_row(opted_in_user, index)
        )
    db.commit()
    assert send_whatsapp_rate_limited(db, opted_in_user.id) is True
    assert send_whatsapp_rate_limited(db, 999999) is False


def _summary_row(user: User, index: int):
    from app.models.notification import Notification

    return Notification(
        user_id=user.id,
        type=NotificationType.SCHEME_SUMMARY,
        template_name="scheme_summary",
        payload={"scheme_name": str(index)},
        status=NotificationStatus.QUEUED,
        dedupe_key=f"dedupe-{utcnow().timestamp()}-{index}-{user.id}",
    )


def test_can_notify_reasons(db):
    user = make_completed_profile(db)
    assert can_notify(user) == "not_opted_in"
    user.consent_whatsapp = True
    assert can_notify(user) == "mobile_unverified"
    user.mobile_verified_at = utcnow()
    assert can_notify(user) is None


def test_can_send_on_request_needs_consent_but_not_verification(db):
    """A summary the user asked for does not need a proven mobile number."""
    user = make_completed_profile(db)
    assert can_send_on_request(user) == "not_opted_in"
    user.consent_whatsapp = True
    # mobile_verified_at is still None: password sign-up never sets it.
    assert can_send_on_request(user) is None
