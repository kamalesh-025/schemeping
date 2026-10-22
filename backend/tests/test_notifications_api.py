"""HTTP behaviour for Phase 5 notifications: prefs, send-to-WhatsApp, webhook.

Celery scheduling is stubbed to a no-op so queueing is observed at the DB
level; delivery semantics live in the task tests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.test_translation_service import make_scheme

WEBHOOK_SECRET = "change-me-whatsapp-webhook-secret"


@pytest.fixture(autouse=True)
def no_schedule(monkeypatch) -> None:
    """Queueing stays at the DB layer; the send task has its own tests."""
    monkeypatch.setattr(
        "app.services.notifications._schedule_send", lambda *a, **kw: None
    )


PROFILE = {
    "name": "Malar Selvam",
    "dob": "1981-02-02",
    "gender": "male",
    "occupation": "farmer",
    "annual_income": 150000,
    "education": None,
    "marital_status": "married",
    "state": "Tamil Nadu",
    "district": "Coimbatore",
    "locality": None,
    "pincode": "641001",
    "language": "ta",
    "data_processing_consent": True,
}


@pytest.fixture
def user(db: Session, logged_in_client: TestClient):
    """The logged-in account with a complete profile, opted in for WhatsApp."""
    from app.models.user import User

    response = logged_in_client.put("/api/v1/me", json=PROFILE)
    assert response.status_code == 200, response.text

    found = db.scalars(select(User)).first()
    assert found is not None
    found.consent_whatsapp = True
    db.commit()
    db.refresh(found)
    return found


def _fresh_notification(row_id: int):
    """Read a row in a brand-new session (API commits in its own session)."""
    from app.core.db import SessionLocal
    from app.models.notification import Notification

    session = SessionLocal()
    try:
        return session.get(Notification, row_id)
    finally:
        session.close()


def _notification(db: Session, user_id: int, **overrides) -> Any:
    from app.models.enums import NotificationStatus, NotificationType
    from app.models.notification import Notification

    values: dict[str, Any] = {
        "user_id": user_id,
        "type": NotificationType.SCHEME_SUMMARY,
        "template_name": "scheme_summary",
        "payload": {"scheme_name": "X"},
        "status": NotificationStatus.QUEUED,
    }
    values.update(overrides)
    row = Notification(**values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ prefs


def test_prefs_default_all_on(logged_in_client: TestClient) -> None:
    response = logged_in_client.get("/api/v1/me/notification-prefs")
    assert response.status_code == 200
    assert response.json() == {
        "new_schemes": True,
        "family_milestones": True,
        "deadlines": True,
        "festival": True,
    }


def test_prefs_toggle_persists(logged_in_client: TestClient) -> None:
    response = logged_in_client.patch(
        "/api/v1/me/notification-prefs", json={"deadlines": False}
    )
    assert response.status_code == 200
    assert response.json()["deadlines"] is False

    # A second patch must merge instead of overwrite the whole record.
    response = logged_in_client.patch(
        "/api/v1/me/notification-prefs", json={"festival": False}
    )
    assert response.json()["deadlines"] is False
    assert response.json()["festival"] is False


def test_prefs_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/me/notification-prefs").status_code == 401


# -------------------------------------------------------------- send whatsapp


def test_send_whatsapp_requires_optin(
    db: Session, logged_in_client: TestClient
) -> None:
    """Without consent: skipped, no row, no 5xx."""
    response = logged_in_client.post("/api/v1/schemes/1/send-whatsapp")
    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped",
        "reason": "not_opted_in",
        "notification_id": None,
    }


def test_send_whatsapp_queues_summary(
    db: Session, user, logged_in_client: TestClient
) -> None:
    scheme = make_scheme(db)
    response = logged_in_client.post(f"/api/v1/schemes/{scheme.id}/send-whatsapp")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["notification_id"]

    from app.models.enums import NotificationStatus

    row = _fresh_notification(body["notification_id"])
    assert row is not None
    assert row.template_name == "scheme_summary"
    assert row.status is NotificationStatus.QUEUED
    assert row.payload["scheme_name"] == "A test scheme"
    assert row.dedupe_key is not None

    # The same 3-minute window dedupes a second tap.
    response = logged_in_client.post(f"/api/v1/schemes/{scheme.id}/send-whatsapp")
    assert response.json()["status"] == "skipped"
    from collections.abc import Sequence

    from app.core.db import SessionLocal
    from app.models.notification import Notification

    session = SessionLocal()
    try:
        rows: Sequence[Notification] = session.scalars(
            select(Notification)
        ).all()
    finally:
        session.close()
    assert len(rows) == 1


def test_send_whatsapp_rate_limited(
    db: Session, user, logged_in_client: TestClient
) -> None:
    for _ in range(10):
        _notification(db, user.id)
    response = logged_in_client.post("/api/v1/schemes/1/send-whatsapp")
    assert response.status_code == 429
    assert "10" in response.json()["detail"]


def test_send_whatsapp_unknown_scheme_404(
    db: Session, user, logged_in_client: TestClient
) -> None:
    response = logged_in_client.post("/api/v1/schemes/999/send-whatsapp")
    assert response.status_code == 404


def test_send_whatsapp_unknown_person_404(
    db: Session, user, logged_in_client: TestClient
) -> None:
    scheme = make_scheme(db)
    response = logged_in_client.post(
        f"/api/v1/schemes/{scheme.id}/send-whatsapp", params={"person": "999"}
    )
    assert response.status_code == 404


# ------------------------------------------------------------------ list


def test_notifications_list_newest_first(
    db: Session, user, logged_in_client: TestClient
) -> None:
    first = _notification(db, user.id)
    second = _notification(db, user.id)
    _notification(db, user.id)

    response = logged_in_client.get("/api/v1/notifications")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert [item["id"] for item in body["notifications"]] == sorted(
        [item["id"] for item in body["notifications"]], reverse=True
    )
    assert first.id < second.id

    response = logged_in_client.get("/api/v1/notifications", params={"limit": 1})
    assert response.json()["total"] == 1


def test_notifications_require_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/notifications").status_code == 401


# ------------------------------------------------------------------ webhook


def test_webhook_rejects_bad_secret(client: TestClient) -> None:
    response = client.post(
        "/api/v1/notifications/webhook",
        json={"message_id": "abc", "status": "delivered"},
        headers={"X-Webhook-Secret": "wrong"},
    )
    assert response.status_code == 403
    # Missing and query-param variants are verified too.
    assert client.post(
        "/api/v1/notifications/webhook", json={"message_id": "abc", "status": "delivered"}
    ).status_code == 403
    ok = client.post(
        "/api/v1/notifications/webhook",
        json={"message_id": "abc", "status": "delivered"},
        params={"secret": WEBHOOK_SECRET},
    )
    assert ok.status_code in (200, 422)  # 422 only if no row matches lookup shape


def test_webhook_updates_delivery_status(
    db: Session, user, client: TestClient
) -> None:
    row = _notification(
        db, user.id, provider_message_id="msg-42", template_name="scheme_summary"
    )
    response = client.post(
        "/api/v1/notifications/webhook",
        json={"message_id": "msg-42", "status": "delivered"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "updated"}

    refreshed = _fresh_notification(row.id)
    assert refreshed is not None
    from app.models.enums import NotificationStatus

    assert refreshed.status is NotificationStatus.DELIVERED
    assert refreshed.delivered_at is not None
    assert refreshed.sent_at is not None


def test_webhook_accepts_msg91_request_id_shape(
    db: Session, user, client: TestClient
) -> None:
    row = _notification(db, user.id, provider_message_id="req-7")
    response = client.post(
        "/api/v1/notifications/webhook",
        json={"payload": {"request_id": "req-7", "dlr_status": "sent"}},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.status_code == 200
    refreshed = _fresh_notification(row.id)
    assert refreshed is not None
    assert refreshed.sent_at is not None


def test_webhook_unknown_message_is_ignored(client: TestClient) -> None:
    response = client.post(
        "/api/v1/notifications/webhook",
        json={"message_id": "no-such", "status": "delivered"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


def test_webhook_unparseable_body_422(client: TestClient) -> None:
    response = client.post(
        "/api/v1/notifications/webhook",
        json={"foo": "bar"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert response.status_code == 422


def test_meta_webhook_challenge_and_signature(
    db: Session,
    user,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    settings = SimpleNamespace(
        whatsapp_provider="meta",
        meta_whatsapp_verify_token="verify-this",
        meta_whatsapp_app_secret="app-secret",
    )
    monkeypatch.setattr("app.api.notifications.get_settings", lambda: settings)

    challenge = client.get(
        "/api/v1/notifications/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "verify-this",
            "hub.challenge": "challenge-value",
        },
    )
    assert challenge.status_code == 200
    assert challenge.text == "challenge-value"
    rejected = client.get(
        "/api/v1/notifications/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-value",
        },
    )
    assert rejected.status_code == 403

    row = _notification(db, user.id, provider_message_id="wamid.meta")
    body = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [{"id": "wamid.meta", "status": "delivered"}]
                        }
                    }
                ]
            }
        ]
    }
    raw_body = json.dumps(body).encode()
    signature = "sha256=" + hmac.new(
        b"app-secret", raw_body, hashlib.sha256
    ).hexdigest()
    delivered = client.post(
        "/api/v1/notifications/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert delivered.status_code == 200
    assert delivered.json() == {"status": "updated"}
    refreshed = _fresh_notification(row.id)
    assert refreshed is not None
    from app.models.enums import NotificationStatus

    assert refreshed.status is NotificationStatus.DELIVERED
