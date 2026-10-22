"""Celery task behaviour for Phase 5 notifications.

Tasks run synchronously with ``task_always_eager`` enabled, so
``queue_notification`` -> ``apply_async`` records through the recording
provider without a broker. Quiet hours are neutralised with a direct
``quiet_hours_delay -> None`` patch.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from tests.conftest import make_completed_profile
from tests.test_translation_service import make_scheme


def _fresh_notification(row_id: int):
    """Read a row in a brand-new session.

    The Celery task commits in its own session; the test session's
    REPEATABLE-READ snapshot can look stale even after ``expire_all``.
    """
    from app.core.db import SessionLocal
    from app.models.notification import Notification

    session = SessionLocal()
    try:
        return session.get(Notification, row_id)
    finally:
        session.close()


@dataclass
class RecordingWhatsApp:
    """The stand-in provider all task assertions read from."""

    sent: list = field(default_factory=list)
    fail_next: int = 0
    counter: int = 0

    def send_template(self, mobile, template_name, params, language="en"):
        if self.fail_next > 0:
            self.fail_next -= 1
            from app.services.messaging import MessagingError

            raise MessagingError("simulated outage")
        self.counter += 1
        self.sent.append(
            {
                "mobile": mobile,
                "template": template_name,
                "params": dict(params),
                "language": language,
            }
        )
        return f"mock-{self.counter}"


@pytest.fixture
def whatsapp(monkeypatch) -> Iterator[RecordingWhatsApp]:
    provider = RecordingWhatsApp()
    provider_module = "app.services.messaging"
    monkeypatch.setattr(f"{provider_module}.get_whatsapp_provider", lambda: provider)
    # Quiet hours would otherwise make sends wait until 8 AM IST.
    monkeypatch.setattr(
        "app.services.notifications.quiet_hours_delay", lambda: None
    )
    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = False
    yield provider
    celery_app.conf.task_always_eager = False
    celery_app.conf.task_eager_propagates = True


def _opted_in(db, mobile: str = "9876543210", name: str = "Lakshmi"):
    from app.core.time import utcnow

    user = make_completed_profile(db, consent_whatsapp=True, mobile=mobile, name=name)
    user.mobile_verified_at = utcnow()
    db.commit()
    return user


# ------------------------------------------------------------------ daily scan


def test_daily_scan_birthday_milestone_once(db, whatsapp):
    """A daughter turning 18 today produces exactly one family_milestone."""
    from app.models.family import FamilyMember
    from app.workers.tasks import daily_eligibility_scan

    today = date.today()
    user = _opted_in(db)
    member = FamilyMember(
        user_id=user.id,
        name="Meena",
        relationship="daughter",
        gender="female",
    )
    db.add(member)
    db.flush()
    # EncryptedString stores whatever is assigned: dates must be date objects.
    member.dob = date(today.year - 18, today.month, today.day)
    db.commit()
    make_scheme(
        db,
        slug="daughter-18",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {
                "all": [
                    {"field": "age", "op": ">=", "value": 18},
                    {"field": "gender", "op": "==", "value": "female"},
                ]
            },
        },
    )
    db.commit()

    daily_eligibility_scan()

    sends = [s for s in whatsapp.sent if s["template"] == "family_milestone"]
    assert len(sends) == 1, whatsapp.sent
    assert sends[0]["params"]["person_name"] == "Meena"
    assert "18" in sends[0]["params"]["milestone_line"]
    assert sends[0]["mobile"] == "9876543210"

    # Running the scan twice queues nothing new.
    whatsapp.sent.clear()
    daily_eligibility_scan()
    assert whatsapp.sent == []


def test_daily_scan_new_scheme_notification(db, whatsapp):
    """A newly published scheme eligible for the head gets one message."""
    from app.services.eligibility import recompute_user
    from app.workers.tasks import daily_eligibility_scan

    user = _opted_in(db)
    make_scheme(
        db,
        slug="age-over-thirty",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {"all": [{"field": "age", "op": ">=", "value": 30}]},
        },
    )
    recompute_user(db, user)  # first snapshot; scheme already eligible

    make_scheme(
        db,
        slug="education-new",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {"all": [{"field": "state", "op": "==", "value": "Tamil Nadu"}]},
        },
    )

    daily_eligibility_scan()
    sends = [s for s in whatsapp.sent if s["template"] == "new_scheme_eligible"]
    assert len(sends) == 1
    assert sends[0]["params"]["scheme_name"] == "A test scheme"

    # Running the scan twice queues nothing new.
    whatsapp.sent.clear()
    daily_eligibility_scan()
    assert whatsapp.sent == []


def test_daily_scan_skips_non_optedin(db, whatsapp):
    """No opt-in means zero sends even for a brand-new scheme."""
    make_completed_profile(db, consent_whatsapp=False)
    make_scheme(
        db,
        slug="always-on",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {"all": [{"field": "age", "op": ">=", "value": 1}]},
        },
    )
    from app.workers.tasks import daily_eligibility_scan

    summary = daily_eligibility_scan()
    assert whatsapp.sent == []
    assert summary["skipped"] >= 1


# ------------------------------------------------------------------ deadlines


def _recompute_everyone(db):
    from app.services.eligibility import recompute_user

    for user in db.scalars(select(User)).all():
        recompute_user(db, user)


from app.models.user import User  # noqa: E402


def test_deadline_reminder_three_days(db, whatsapp):
    from app.workers.tasks import deadline_reminders

    make_scheme(db, slug="deadline-soon", deadline=date.today() + timedelta(days=3))
    _opted_in(db)
    _recompute_everyone(db)

    deadline_reminders()
    reminders = [s for s in whatsapp.sent if s["template"] == "deadline_reminder"]
    assert len(reminders) == 1, whatsapp.sent
    assert "3 days left" in reminders[0]["params"]["days_left"]

    # Re-running the job cannot double-remind.
    whatsapp.sent.clear()
    deadline_reminders()
    assert whatsapp.sent == []


def test_deadline_reminder_ignores_other_offsets(db, whatsapp):
    from app.workers.tasks import deadline_reminders

    make_scheme(db, slug="deadline-far", deadline=date.today() + timedelta(days=10))
    _opted_in(db)
    _recompute_everyone(db)

    deadline_reminders()
    assert [s for s in whatsapp.sent if s["template"] == "deadline_reminder"] == []


def test_deadline_reminder_requires_optin(db, whatsapp):
    from app.workers.tasks import deadline_reminders

    make_scheme(db, slug="deadline-nonoptin", deadline=date.today() + timedelta(days=1))
    make_completed_profile(db, consent_whatsapp=False)
    _recompute_everyone(db)

    deadline_reminders()
    assert [s for s in whatsapp.sent if s["template"] == "deadline_reminder"] == []


# ------------------------------------------------------------------ festival


def test_festival_broadcast_once(db, whatsapp):
    from app.workers.tasks import festival_benefit_broadcast

    scheme = make_scheme(db, slug="festival-cash", benefit_amount="₹5000")
    _opted_in(db)

    festival_benefit_broadcast(scheme.id)
    festival = [s for s in whatsapp.sent if s["template"] == "festival_benefit"]
    assert len(festival) == 1
    assert "₹5000" in festival[0]["params"]["benefit"]

    # Re-running the broadcast cannot double-send.
    whatsapp.sent.clear()
    festival_benefit_broadcast(scheme.id)
    assert whatsapp.sent == []


# ------------------------------------------------------------------ sending


def _queued_row(db, user):
    from app.models.enums import NotificationStatus, NotificationType
    from app.models.notification import Notification

    row = Notification(
        user_id=user.id,
        type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="new_scheme_eligible",
        payload={
            "person_name_line": "",
            "scheme_name": "X",
            "benefit": "₹1",
            "deadline_line": "y",
        },
        status=NotificationStatus.QUEUED,
    )
    db.add(row)
    db.commit()
    return row


def test_send_notification_records_provider_id(db, whatsapp):
    from app.models.enums import NotificationStatus
    from app.workers.tasks import send_notification

    user = _opted_in(db)
    row = _queued_row(db, user)
    result = send_notification(row.id)

    assert result["status"] == "sent"
    refreshed = _fresh_notification(row.id)
    assert refreshed.status is NotificationStatus.SENT
    assert refreshed.provider_message_id
    assert refreshed.sent_at is not None
    assert whatsapp.sent[-1]["template"] == "new_scheme_eligible"


def test_send_notification_exhausts_retries_then_fails(db, whatsapp):
    from app.models.enums import NotificationStatus
    from app.workers.tasks import send_notification

    user = _opted_in(db)
    row = _queued_row(db, user)
    whatsapp.fail_next = 5

    result = send_notification.apply_async([row.id]).get()
    assert result["status"] == "failed"
    refreshed = _fresh_notification(row.id)
    assert refreshed.status is NotificationStatus.FAILED
    assert "simulated outage" in refreshed.error


def test_send_notification_respects_revoked_optin(db, whatsapp):
    from app.models.enums import NotificationStatus
    from app.workers.tasks import send_notification

    user = _opted_in(db)
    row = _queued_row(db, user)
    user.consent_whatsapp = False
    db.commit()

    result = send_notification(row.id)
    assert result["status"] == "blocked"
    refreshed = _fresh_notification(row.id)
    assert refreshed.status is NotificationStatus.FAILED
    assert whatsapp.sent == []


def test_send_notification_unknown_template_fails(db, whatsapp):
    from app.models.enums import NotificationStatus, NotificationType
    from app.models.notification import Notification
    from app.services.messaging import MessagingError
    from app.workers.tasks import send_notification

    user = _opted_in(db)
    row = Notification(
        user_id=user.id,
        type=NotificationType.NEW_SCHEME_ELIGIBLE,
        template_name="not_a_template",
        payload={},
        status=NotificationStatus.QUEUED,
    )
    db.add(row)
    db.commit()

    with pytest.raises(MessagingError):
        send_notification(row.id)
