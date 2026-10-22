"""Password sign-up and sign-in (the default auth mode, no SMS vendor)."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.core.time import utcnow
from app.models.refresh_token import RefreshToken
from app.models.user import User
from sqlalchemy import func, select

PASSWORD = "schemeping-test-password"
MOBILE = "9876543210"


def _register(client, mobile: str = MOBILE, password: str = PASSWORD, **extra):
    return client.post(
        "/api/v1/auth/register",
        json={"mobile": mobile, "password": password, **extra},
    )


def _login(client, mobile: str = MOBILE, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"mobile": mobile, "password": password}
    )


def test_auth_config_defaults_to_password_mode(client) -> None:
    body = client.get("/api/v1/auth/config").json()

    assert body["mode"] == "password"
    assert body["password_min_length"] >= 8
    assert body["widget_id"] is None


def test_registration_creates_an_account_and_starts_a_session(client, db) -> None:
    response = _register(client)

    assert response.status_code == 201, response.text
    assert response.json()["mobile"] == MOBILE
    assert response.json()["profile_complete"] is False

    user = db.scalar(select(User).where(User.mobile == MOBILE))
    assert user is not None
    assert user.password_hash is not None
    assert user.password_hash.startswith("scrypt$")
    # No SMS was sent, so nothing proved ownership of the number.
    assert user.mobile_verified_at is None

    assert client.get("/api/v1/auth/session").json()["mobile"] == MOBILE


def test_registration_normalises_a_country_code(client) -> None:
    response = _register(client, mobile="+91 98765 43210")

    assert response.status_code == 201, response.text
    assert response.json()["mobile"] == MOBILE


def test_registration_rejects_a_duplicate_mobile(client) -> None:
    assert _register(client).status_code == 201

    duplicate = _register(client)

    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_registration_enforces_the_minimum_password_length(client) -> None:
    response = _register(client, password="short")

    assert response.status_code == 422


def test_the_password_hash_never_leaves_the_server(client) -> None:
    response = _register(client)
    serialised = response.text + client.get("/api/v1/auth/session").text

    assert "password" not in serialised.lower()
    assert "scrypt" not in serialised


def test_login_with_the_right_password_starts_a_session(client, db) -> None:
    assert _register(client).status_code == 201
    client.cookies.clear()

    response = _login(client)

    assert response.status_code == 200, response.text
    assert response.json()["mobile"] == MOBILE
    assert client.get("/api/v1/auth/session").status_code == 200


def test_a_wrong_password_and_an_unknown_number_give_the_same_answer(client) -> None:
    assert _register(client).status_code == 201
    client.cookies.clear()

    wrong_password = _login(client, password="not-the-right-password")
    unknown_number = _login(client, mobile="9000000001")

    assert wrong_password.status_code == 401
    assert unknown_number.status_code == 401
    # Identical text: the API must not reveal which numbers have accounts.
    assert wrong_password.json()["detail"] == unknown_number.json()["detail"]


def test_login_never_creates_an_account(client, db) -> None:
    response = _login(client, mobile="9000000001")

    assert response.status_code == 401
    assert db.scalar(select(func.count()).select_from(User)) == 0


def test_repeated_failures_for_one_number_are_rate_limited(client) -> None:
    assert _register(client).status_code == 201
    client.cookies.clear()

    statuses = [_login(client, password="wrong-password").status_code for _ in range(10)]
    blocked = _login(client, password="wrong-password")

    assert set(statuses) == {401}
    assert blocked.status_code == 429
    # Even the correct password is refused while the budget is exhausted.
    assert _login(client).status_code == 429


def test_changing_the_password_keeps_this_device_and_signs_out_others(
    client, db
) -> None:
    from app.main import create_app
    from fastapi.testclient import TestClient

    assert _register(client).status_code == 201
    phone = TestClient(create_app())
    phone.__enter__()
    try:
        assert _login(phone).status_code == 200

        response = client.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": "a-brand-new-password"},
        )

        assert response.status_code == 204, response.text
        # This device keeps working.
        assert client.post("/api/v1/auth/refresh").status_code == 200
        # The other device's refresh token was revoked.
        assert phone.post("/api/v1/auth/refresh").status_code == 401
    finally:
        phone.__exit__(None, None, None)

    db.expire_all()
    live = db.scalars(
        select(RefreshToken).where(
            RefreshToken.revoked_at.is_(None),
            RefreshToken.rotated_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
    ).all()
    assert len(live) == 1

    other = TestClient(create_app())
    other.__enter__()
    try:
        assert _login(other).status_code == 401
        assert _login(other, password="a-brand-new-password").status_code == 200
    finally:
        other.__exit__(None, None, None)


def test_changing_the_password_requires_the_current_one(client) -> None:
    assert _register(client).status_code == 201

    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-my-password", "new_password": "another-password"},
    )

    assert response.status_code == 400
    assert "Current password" in response.json()["detail"]
    # The old password still works, so nothing changed.
    client.cookies.clear()
    assert _login(client).status_code == 200


def test_changing_the_password_requires_a_session(client) -> None:
    response = client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "another-password"},
    )

    assert response.status_code == 401


def test_otp_endpoints_are_closed_in_password_mode(client) -> None:
    request = client.post("/api/v1/auth/otp/request", json={"mobile": MOBILE})
    verify = client.post(
        "/api/v1/auth/otp/verify", json={"mobile": MOBILE, "otp": "123456"}
    )

    assert request.status_code == 409
    assert verify.status_code == 409


def test_password_endpoints_are_closed_in_otp_mode(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "auth_mode", "otp", raising=False)

    assert _register(client).status_code == 409
    assert _login(client).status_code == 409
