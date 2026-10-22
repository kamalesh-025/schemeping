"""Session lifecycle: cookies, refresh rotation, replay detection, logout."""

from __future__ import annotations

from app.core.config import get_settings
from app.models.refresh_token import RefreshToken


def _login(client, mobile: str = "9876543210"):
    """Register (which signs in) and return the session response."""
    return client.post(
        "/api/v1/auth/register",
        json={"mobile": mobile, "password": "schemeping-test-password"},
    )


def test_login_sets_httponly_cookies(client) -> None:
    response = _login(client)
    assert response.status_code == 201

    settings = get_settings()
    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith(settings.access_cookie_name))
    refresh = next(c for c in cookies if c.startswith(settings.refresh_cookie_name))

    for header in (access, refresh):
        assert "HttpOnly" in header
        assert "Path=/" in header
        assert "SameSite=lax" in header or "samesite=lax" in header.lower()

    body = response.json()
    assert body["profile_complete"] is False
    assert body["has_consent"] is False


def test_access_token_is_not_returned_in_the_body(client) -> None:
    response = _login(client)
    serialised = response.text
    assert "access_token" not in serialised
    assert "refresh_token" not in serialised
    assert "." not in response.json()["mobile"]  # no accidental JWT leakage


def test_profile_route_requires_authentication(client) -> None:
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/family").status_code == 401


def test_session_after_login_returns_the_user(logged_in_client) -> None:
    response = logged_in_client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["mobile"] == "9876543210"


def test_refresh_rotates_the_token_and_old_token_reuse_revokes_family(
    client, otp_provider, db
) -> None:
    _login(client)
    settings = get_settings()
    original_refresh = client.cookies.get(settings.refresh_cookie_name)

    # First refresh rotates.
    first = client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    rotated_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert rotated_refresh != original_refresh

    rows = db.query(RefreshToken).all()
    assert len(rows) == 2
    db.rollback()

    # Replaying the original token is treated as theft.
    headers = {"Cookie": f"{settings.refresh_cookie_name}={original_refresh}"}
    replay = client.post("/api/v1/auth/refresh", headers=headers)
    assert replay.status_code == 401

    # The whole family is now revoked, so the newest token is dead too.
    db.rollback()
    assert all(row.revoked_at is not None for row in db.query(RefreshToken).all())


def test_refresh_without_cookie_is_unauthorized(client) -> None:
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_the_refresh_token(client, db) -> None:
    _login(client)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204

    db.rollback()
    assert all(row.revoked_at is not None for row in db.query(RefreshToken).all())
    # Cookies were cleared, so a silent refresh can no longer succeed.
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_access_token_works_via_bearer_header_for_api_clients(
    client, otp_provider
) -> None:
    _login(client)
    settings = get_settings()
    access = client.cookies.get(settings.access_cookie_name)
    client.cookies.clear()

    response = client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    assert response.status_code == 200


def test_mobile_is_not_logged_in_plaintext(client, capsys) -> None:
    _login(client)
    captured = capsys.readouterr().out
    assert "9876543210" not in captured or "98******10" in captured
