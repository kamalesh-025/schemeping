"""Admin panel: separate auth with TOTP 2FA, roles, audit trail, workflow."""

from __future__ import annotations

import time

from app.services import admin_auth
from fastapi.testclient import TestClient
from sqlalchemy import select

BASE = "/api/v1/admin-panel"


def _totp_now(secret: str) -> str:
    """The code the authenticator app would show right now."""
    counter = int(time.time() // 30)
    return admin_auth._totp_code(secret, counter)


def _bootstrap(client: TestClient, username: str = "publisher", role: str = "publisher"):
    response = client.post(
        f"{BASE}/bootstrap",
        json={"username": username, "password": "correct-horse-battery", "role": role},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _admin_row(db, username: str = "publisher"):
    from app.models.admin import AdminUser

    return db.scalar(select(AdminUser).where(AdminUser.username == username))


def _login(client: TestClient, db, username: str = "publisher", role: str = "publisher"):
    _bootstrap(client, username, role)
    row = _admin_row(db, username)
    assert row is not None
    response = client.post(
        f"{BASE}/login",
        json={
            "username": username,
            "password": "correct-horse-battery",
            "totp": _totp_now(row.totp_secret),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ auth


def test_status_reports_bootstrap_need(client: TestClient):
    response = client.get(f"{BASE}/status")
    assert response.status_code == 200
    assert response.json() == {"needs_bootstrap": True}


def test_bootstrap_creates_first_admin(client: TestClient, db):
    created = _bootstrap(client)
    assert created["role"] == "publisher"
    assert _admin_row(db) is not None


def test_bootstrap_only_once(client: TestClient, db):
    _bootstrap(client)
    response = client.post(
        f"{BASE}/bootstrap",
        json={"username": "second", "password": "another-password", "role": "editor"},
    )
    assert response.status_code == 409


def test_login_requires_password_and_totp(client: TestClient, db):
    _bootstrap(client)
    row = _admin_row(db)

    wrong_password = client.post(
        f"{BASE}/login",
        json={"username": "publisher", "password": "nope", "totp": _totp_now(row.totp_secret)},
    )
    assert wrong_password.status_code == 401

    wrong_totp = client.post(
        f"{BASE}/login",
        json={"username": "publisher", "password": "correct-horse-battery", "totp": "000000"},
    )
    assert wrong_totp.status_code == 401


def test_login_with_2fa_returns_token(client: TestClient, db):
    token = _login(client, db)
    assert token


def test_non_admin_cannot_reach_the_panel(client: TestClient, db):
    token = _login(client, db)
    assert client.get(f"{BASE}/schemes", headers=_auth(token)).status_code == 200
    # No token at all.
    assert client.get(f"{BASE}/schemes").status_code == 401
    # A citizen access token is not an admin token.
    from app.core.security import create_access_token

    citizen = create_access_token(1)
    assert (
        client.get(f"{BASE}/schemes", headers=_auth(citizen)).status_code == 401
    )


def test_editor_cannot_publish(client: TestClient, db):
    _bootstrap(client, "editor-user", "editor")
    row = _admin_row(db, "editor-user")
    response = client.post(
        f"{BASE}/login",
        json={
            "username": "editor-user",
            "password": "correct-horse-battery",
            "totp": _totp_now(row.totp_secret),
        },
    )
    token = response.json()["token"]
    draft = client.post(
        f"{BASE}/schemes",
        json=_scheme_payload(),
        headers=_auth(token),
    )
    assert draft.status_code == 200
    publish = client.post(
        f"{BASE}/schemes/{draft.json()['id']}/publish", headers=_auth(token)
    )
    assert publish.status_code == 403


# ------------------------------------------------------------------ schemes


def _scheme_payload(**overrides) -> dict:
    values = {
        "slug": "admin-created-scheme",
        "name": "Admin Created Scheme",
        "department": "Test Department",
        "level": "state",
        "state": "Tamil Nadu",
        "category": "education",
        "scope": "individual",
        "benefit_summary": "Supports students.",
        "benefit_amount": "₹2,000",
        "benefit_type": "cash",
        "eligibility_rules": {
            "applies_to": "individual",
            "rules": {"all": [{"field": "age", "op": ">=", "value": 18}]},
        },
        "required_documents": [{"name": "Aadhaar card", "notes": None}],
        "application_steps": [{"order": 1, "title": "Collect documents", "description": "x"}],
        "apply_url": "https://example.com/apply",
        "deadline": None,
        "source_url": "https://source.example/scheme",
        "priority": 50,
    }
    values.update(overrides)
    return values


def test_create_scheme_is_a_draft(client: TestClient, db):
    token = _login(client, db)
    response = client.post(f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "draft"


def test_create_scheme_rejects_invalid_rules(client: TestClient, db):
    token = _login(client, db)
    response = client.post(
        f"{BASE}/schemes",
        json=_scheme_payload(eligibility_rules={"nonsense": True}),
        headers=_auth(token),
    )
    assert response.status_code == 422


def test_update_scheme_records_the_change(client: TestClient, db):
    token = _login(client, db)
    created = client.post(
        f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token)
    ).json()
    updated = client.put(
        f"{BASE}/schemes/{created['id']}",
        json=_scheme_payload(name="Renamed Scheme"),
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed Scheme"

    logs = client.get(f"{BASE}/audit-logs", headers=_auth(token)).json()
    actions = [log["action"] for log in logs["logs"]]
    assert "create" in actions
    assert "update" in actions
    update_log = next(log for log in logs["logs"] if log["action"] == "update")
    assert update_log["admin_id"] == "publisher"
    assert update_log["entity"] == "scheme"


def test_publish_sets_verified_date_and_recomputes(client: TestClient, db):
    from app.core.db import SessionLocal
    from app.models.scheme import Scheme

    token = _login(client, db)
    created = client.post(
        f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token)
    ).json()
    response = client.post(
        f"{BASE}/schemes/{created['id']}/publish", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    assert response.json()["last_verified_on"]

    session = SessionLocal()
    try:
        scheme = session.get(Scheme, created["id"])
        assert scheme is not None
        assert scheme.last_verified_on is not None
        assert str(getattr(scheme.status, "value", scheme.status)) == "published"
    finally:
        session.close()


def test_publishing_twice_is_rejected(client: TestClient, db):
    token = _login(client, db)
    created = client.post(
        f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token)
    ).json()
    client.post(f"{BASE}/schemes/{created['id']}/publish", headers=_auth(token))
    again = client.post(
        f"{BASE}/schemes/{created['id']}/publish", headers=_auth(token)
    )
    assert again.status_code == 409


def test_archive_scheme(client: TestClient, db):
    token = _login(client, db)
    created = client.post(
        f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token)
    ).json()
    response = client.post(
        f"{BASE}/schemes/{created['id']}/archive", headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["status"] == "archived"


# ------------------------------------------------------------------ rule testing


def test_rule_test_against_a_sample_profile(client: TestClient, db):
    token = _login(client, db)
    response = client.post(
        f"{BASE}/rules/test",
        json={
            "rules": {
                "applies_to": "individual",
                "rules": {"all": [{"field": "age", "op": ">=", "value": 18}]},
            },
            "sample_profile": {"dob": "1990-01-01", "state": "Tamil Nadu"},
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True
    assert body["status"] == "eligible"


def test_rule_test_reports_invalid_rules(client: TestClient, db):
    token = _login(client, db)
    response = client.post(
        f"{BASE}/rules/test",
        json={"rules": {"bad": []}, "sample_profile": {}},
        headers=_auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["errors"]


# ------------------------------------------------------------------ facilities


def test_facility_create_and_update(client: TestClient, db):
    token = _login(client, db)
    payload = {
        "name": "CSC Erode Town",
        "kind": "csc",
        "address": "Main Bazaar, Erode",
        "district": "Erode",
        "state": "Tamil Nadu",
        "latitude": 11.34,
        "longitude": 77.72,
        "working_hours": "Mon-Fri 10am-5pm",
        "phone": "0424-2222222",
    }
    created = client.post(f"{BASE}/facilities", json=payload, headers=_auth(token))
    assert created.status_code == 200, created.text
    updated = client.put(
        f"{BASE}/facilities/{created.json()['id']}",
        json={**payload, "name": "CSC Erode Main"},
        headers=_auth(token),
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "CSC Erode Main"


# ------------------------------------------------------------------ audit log


def test_audit_log_is_read_only(client: TestClient, db):
    token = _login(client, db)
    for method in ("post", "put", "patch", "delete"):
        response = client.request(
            method.upper(), f"{BASE}/audit-logs", json={}, headers=_auth(token)
        )
        assert response.status_code == 405, method


def test_audit_log_records_admin_actions(client: TestClient, db):
    token = _login(client, db)
    client.post(f"{BASE}/schemes", json=_scheme_payload(), headers=_auth(token))
    logs = client.get(f"{BASE}/audit-logs", headers=_auth(token)).json()
    assert logs["total"] >= 2  # bootstrap + create
    create_log = next(log for log in logs["logs"] if log["action"] == "create")
    assert create_log["entity"] == "scheme"
    assert create_log["diff"]
