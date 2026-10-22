"""The SQLAdmin panel: staff login with 2FA, and no citizen access."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


def _totp_now(secret: str) -> str:
    from app.services import admin_auth

    return admin_auth._totp_code(secret, int(time.time() // 30))


@pytest.fixture
def admin_account(db):
    from app.models.admin import AdminUser
    from app.services import admin_auth

    admin = AdminUser(
        username="staff",
        password_hash=admin_auth.hash_password("correct-horse-battery"),
        role="publisher",
        totp_secret=admin_auth.generate_totp_secret(),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def test_admin_panel_requires_login(client: TestClient, admin_account):
    """A visitor without a staff session is sent to the login page."""
    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert "/admin/login" in response.headers.get("location", "")


def test_admin_login_page_is_public(client: TestClient, admin_account):
    response = client.get("/admin/login")
    assert response.status_code == 200
    assert "totp" in response.text.lower()


def test_login_with_password_and_2fa(client: TestClient, admin_account):
    response = client.post(
        "/admin/login",
        data={
            "username": "staff",
            "password": "correct-horse-battery",
            "totp": _totp_now(admin_account.totp_secret),
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303, 307), response.text


def test_login_without_2fa_is_rejected(client: TestClient, admin_account):
    response = client.post(
        "/admin/login",
        data={"username": "staff", "password": "correct-horse-battery", "totp": ""},
        follow_redirects=False,
    )
    # sqladmin answers 400 for a rejected login.
    assert response.status_code in (200, 302, 303, 307, 400)
    # Still not logged in: the panel must not open.
    panel = client.get("/admin/", follow_redirects=False)
    assert panel.status_code in (302, 303, 307)
    assert "/admin/login" in panel.headers.get("location", "")


def test_wrong_password_is_rejected(client: TestClient, admin_account):
    client.post(
        "/admin/login",
        data={
            "username": "staff",
            "password": "wrong",
            "totp": _totp_now(admin_account.totp_secret),
        },
        follow_redirects=False,
    )
    panel = client.get("/admin/", follow_redirects=False)
    assert panel.status_code in (302, 303, 307)
    assert "/admin/login" in panel.headers.get("location", "")
