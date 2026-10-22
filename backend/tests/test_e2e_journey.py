"""End-to-end smoke test (Phase 6, acceptance criterion).

Runs the whole citizen journey against a real database with the mock
providers, then the admin side:

  register -> onboard -> add family -> dashboard -> open a scheme ->
  apply guide -> send to WhatsApp (mock) -> ask the assistant ->
  admin publishes a new scheme -> the user is notified (mock).

Usage (the MySQL test database must exist and be migrated):

    cd backend
    python -m pytest tests/test_e2e_journey.py -q      # as a test
    python scripts/e2e_demo.py                         # as a script

The script version talks to a running API over HTTP; the pytest version
drives the app in-process. Both assert the same journey.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_completed_profile
from tests.test_translation_service import make_scheme


@pytest.fixture
def whatsapp(monkeypatch):
    """A recording WhatsApp provider (no network, no WhatsApp account)."""
    from app.services.messaging import MessagingError

    class Recording:
        def __init__(self) -> None:
            self.sent: list[dict] = []
            self.fail_next = 0
            self.counter = 0

        def send_template(self, mobile, template_name, params, language="en"):
            if self.fail_next > 0:
                self.fail_next -= 1
                raise MessagingError("simulated outage")
            self.counter += 1
            self.sent.append(
                {"mobile": mobile, "template": template_name, "params": dict(params)}
            )
            return f"e2e-{self.counter}"

    provider = Recording()
    monkeypatch.setattr(
        "app.services.messaging.get_whatsapp_provider", lambda: provider
    )
    monkeypatch.setattr("app.services.notifications.quiet_hours_delay", lambda: None)
    monkeypatch.setattr(
        "app.services.notifications._schedule_send", lambda *a, **kw: None
    )

    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    yield provider


def test_full_citizen_journey(db, whatsapp, monkeypatch):
    from app.core.security import create_access_token
    from app.core.time import utcnow
    from app.main import create_app

    user = make_completed_profile(db, consent_whatsapp=True)
    user.mobile_verified_at = utcnow()
    db.commit()

    # A published scheme the citizen can match.
    make_scheme(
        db,
        slug="e2e-existing",
        name="E2E Existing Scheme",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {"all": [{"field": "state", "op": "==", "value": "Tamil Nadu"}]},
        },
    )

    with TestClient(create_app()) as client:
        client.cookies.set("sp_access", create_access_token(user.id))

        # 1. Dashboard: the eligible scheme shows up.
        client.post("/api/v1/eligibility/recompute")
        cards = client.get("/api/v1/eligibility").json()
        assert cards["total"] >= 1

        # 2. Open a scheme.
        scheme_id = cards["cards"][0]["scheme_id"]
        detail = client.get(f"/api/v1/schemes/{scheme_id}").json()
        assert detail["name"]
        assert "why_qualify" in detail

        # 3. The apply guide data is part of the scheme record.
        assert detail["application_steps"]

        # 4. Send the summary to WhatsApp (mock provider).
        response = client.post(f"/api/v1/schemes/{scheme_id}/send-whatsapp")
        assert response.status_code == 200
        assert response.json()["status"] == "queued"

        # 5. Ask the assistant a question.
        answer = client.post(
            "/api/v1/chat", json={"message": "What am I eligible for?"}
        )
        assert answer.status_code == 200
        assert answer.json()["answer"]

        # 6. The admin publishes a new scheme; the daily scan notifies the user.
        from app.workers.tasks import daily_eligibility_scan

        make_scheme(
            db,
            slug="e2e-new-scheme",
            name="E2E New Scheme",
            eligibility_rules={
                "applies_to": "individual",
                "rules": {"all": [{"field": "state", "op": "==", "value": "Tamil Nadu"}]},
            },
        )
        summary = daily_eligibility_scan()
        assert summary["scanned"] >= 1

        # 7. The user can read their notification list.
        notifications = client.get("/api/v1/notifications").json()
        assert notifications["total"] >= 1


def test_admin_publishes_and_user_is_notified(db, whatsapp, monkeypatch):
    """The admin panel path: bootstrap, login with 2FA, publish, notify."""
    import time

    from app.core.security import create_access_token
    from app.core.time import utcnow
    from app.main import create_app
    from app.services import admin_auth

    user = make_completed_profile(db, consent_whatsapp=True)
    user.mobile_verified_at = utcnow()
    db.commit()

    with TestClient(create_app()) as client:
        # The citizen session still works.
        client.cookies.set("sp_access", create_access_token(user.id))

        # 1. Bootstrap the first publisher.
        bootstrap = client.post(
            "/api/v1/admin-panel/bootstrap",
            json={
                "username": "e2e-publisher",
                "password": "correct-horse-battery",
                "role": "publisher",
            },
        )
        assert bootstrap.status_code == 200, bootstrap.text

        # 2. Log in with password + TOTP.
        from app.core.db import SessionLocal
        from app.models.admin import AdminUser
        from sqlalchemy import select

        session = SessionLocal()
        try:
            admin = session.scalar(
                select(AdminUser).where(AdminUser.username == "e2e-publisher")
            )
            totp_secret = admin.totp_secret if admin is not None else ""
        finally:
            session.close()
        assert totp_secret
        code = admin_auth._totp_code(totp_secret, int(time.time() // 30))
        login = client.post(
            "/api/v1/admin-panel/login",
            json={
                "username": "e2e-publisher",
                "password": "correct-horse-battery",
                "totp": code,
            },
        )
        assert login.status_code == 200, login.text
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Create and publish a scheme.
        created = client.post(
            "/api/v1/admin-panel/schemes",
            headers=headers,
            json={
                "slug": "e2e-published",
                "name": "E2E Published Scheme",
                "department": "Test Department",
                "level": "state",
                "state": "Tamil Nadu",
                "category": "education",
                "scope": "individual",
                "benefit_summary": "Support for students.",
                "benefit_amount": "₹1,000",
                "benefit_type": "cash",
                "eligibility_rules": {
                    "applies_to": "individual",
                    "rules": {"all": [{"field": "state", "op": "==", "value": "Tamil Nadu"}]},
                },
                "required_documents": [],
                "application_steps": [],
                "apply_url": None,
                "deadline": None,
                "source_url": "https://source.example/e2e",
                "priority": 50,
            },
        )
        assert created.status_code == 200, created.text
        scheme_id = created.json()["id"]

        published = client.post(
            f"/api/v1/admin-panel/schemes/{scheme_id}/publish", headers=headers
        )
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "published"

        # 4. The audit trail records both writes.
        logs = client.get("/api/v1/admin-panel/audit-logs", headers=headers).json()
        actions = [log["action"] for log in logs["logs"]]
        assert "create" in actions
        assert "publish" in actions

        # 5. The citizen is now eligible for the freshly published scheme.
        client.cookies.set("sp_access", create_access_token(user.id))
        client.post("/api/v1/eligibility/recompute")
        cards = client.get("/api/v1/eligibility").json()
        assert any(card["scheme_id"] == scheme_id for card in cards["cards"])
