"""Analytics events and the privacy endpoints (export + consent view)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import select


def test_event_is_recorded(logged_in_client: TestClient, db):
    from app.models.analytics import AnalyticsEvent

    from tests.test_translation_service import make_scheme

    scheme = make_scheme(db)
    response = logged_in_client.post(
        "/api/v1/events", json={"kind": "scheme_view", "scheme_id": scheme.id}
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"recorded": True, "kind": "scheme_view"}

    rows = db.scalars(select(AnalyticsEvent)).all()
    if not rows:  # the API committed in its own session
        from app.core.db import SessionLocal

        session = SessionLocal()
        try:
            rows = session.scalars(select(AnalyticsEvent)).all()
        finally:
            session.close()
    assert len(rows) == 1
    assert rows[0].kind == "scheme_view"
    assert rows[0].scheme_id == scheme.id


def test_event_requires_authentication(client: TestClient):
    assert client.post("/api/v1/events", json={"kind": "scheme_view"}).status_code == 401


def test_event_kind_is_validated(logged_in_client: TestClient):
    response = logged_in_client.post("/api/v1/events", json={"kind": "nonsense"})
    assert response.status_code == 422


def test_consent_view(logged_in_client: TestClient, db):
    from app.models.user import User

    user = db.scalars(select(User)).first()
    user.consent_whatsapp = True
    user.consent_version = "2026-01"
    db.commit()

    response = logged_in_client.get("/api/v1/me/consents")
    assert response.status_code == 200
    body = response.json()
    assert body["whatsapp"] is True
    assert body["policy_version"] == "2026-01"
    assert set(body["notification_preferences"]) == {
        "new_schemes",
        "family_milestones",
        "deadlines",
        "festival",
    }


def test_data_export_contains_everything(logged_in_client: TestClient, db):
    from app.models.chat import ChatMessage
    from app.models.enums import ChatRole
    from app.models.user import User

    user = db.scalars(select(User)).first()
    db.add(
        ChatMessage(
            user_id=user.id,
            role=ChatRole.USER,
            content="hello there",
        )
    )
    db.commit()

    response = logged_in_client.get("/api/v1/me/export")
    assert response.status_code == 200
    assert "attachment" in response.headers.get("content-disposition", "")
    body = json.loads(response.text)
    assert body["account"]["mobile"]
    assert body["chat_messages"][0]["content"] == "hello there"
    assert "family_members" in body
    assert "eligibility_results" in body
    assert "notifications" in body


def test_export_requires_authentication(client: TestClient):
    assert client.get("/api/v1/me/export").status_code == 401
    assert client.get("/api/v1/me/consents").status_code == 401
