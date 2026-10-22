"""MSG91 OTP Widget sign-in: the DLT-free OTP path.

In widget mode MSG91 sends and verifies the code in the browser, so the backend
never sees the OTP. These tests pin the two rules that make that safe:

- the client cannot choose who it logs in as (the mobile comes from MSG91);
- a rejected or forged token never creates an account or a session.
"""

from __future__ import annotations

import httpx
import pytest
from app.core.config import get_settings
from app.models.user import User
from sqlalchemy import func, select


@pytest.fixture(autouse=True)
def _otp_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the OTP flow; password is the product default."""
    monkeypatch.setattr(get_settings(), "auth_mode", "otp", raising=False)


def _widget_mode(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    settings = get_settings()
    values: dict[str, object] = {
        "messaging_provider": "msg91_widget",
        "msg91_auth_key": "auth-key",
        "msg91_widget_id": "widget-id",
        "msg91_widget_token": "widget-public-token",
    }
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value, raising=False)


def _respond(monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]) -> None:
    monkeypatch.setattr(
        "app.services.messaging.httpx.post",
        lambda url, **kwargs: httpx.Response(
            200, json=payload, request=httpx.Request("POST", url)
        ),
    )


def test_otp_config_defaults_to_the_server_flow(client) -> None:
    body = client.get("/api/v1/auth/config").json()

    assert body["mode"] == "server"
    assert body["widget_id"] is None
    assert body["widget_token"] is None


def test_otp_config_exposes_the_widget_but_never_the_auth_key(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _widget_mode(monkeypatch)

    body = client.get("/api/v1/auth/config").json()

    assert body["mode"] == "widget"
    assert body["widget_id"] == "widget-id"
    assert body["widget_token"] == "widget-public-token"
    assert "auth-key" not in str(body)


def test_server_otp_endpoints_refuse_when_the_widget_owns_verification(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    _widget_mode(monkeypatch)

    request = client.post("/api/v1/auth/otp/request", json={"mobile": "9876543210"})
    verify = client.post(
        "/api/v1/auth/otp/verify", json={"mobile": "9876543210", "otp": "123456"}
    )

    assert request.status_code == 409
    assert verify.status_code == 409


def test_widget_verify_starts_a_session_for_the_number_msg91_verified(
    client, monkeypatch: pytest.MonkeyPatch, db
) -> None:
    _widget_mode(monkeypatch)
    _respond(monkeypatch, {"type": "success", "message": "919876543210"})

    response = client.post(
        "/api/v1/auth/otp/widget/verify", json={"access_token": "widget-access-token"}
    )

    assert response.status_code == 200, response.text
    assert response.json()["mobile"] == "9876543210"

    user = db.scalar(select(User).where(User.mobile == "9876543210"))
    assert user is not None
    assert user.mobile_verified_at is not None

    # The session works exactly like a password-less OTP session.
    assert client.get("/api/v1/auth/session").json()["mobile"] == "9876543210"


def test_widget_verify_ignores_any_mobile_sent_by_the_client(
    client, monkeypatch: pytest.MonkeyPatch, db
) -> None:
    """A caller must not be able to log in as somebody else."""
    _widget_mode(monkeypatch)
    _respond(monkeypatch, {"type": "success", "message": "919876543210"})

    response = client.post(
        "/api/v1/auth/otp/widget/verify",
        json={"access_token": "widget-access-token", "mobile": "9000000001"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["mobile"] == "9876543210"
    assert db.scalar(select(func.count()).select_from(User)) == 1


def test_widget_verify_rejects_a_forged_token_without_creating_an_account(
    client, monkeypatch: pytest.MonkeyPatch, db
) -> None:
    _widget_mode(monkeypatch)
    _respond(monkeypatch, {"type": "error", "message": "AuthenticationFailure", "code": "201"})

    response = client.post(
        "/api/v1/auth/otp/widget/verify", json={"access_token": "forged-token"}
    )

    assert response.status_code == 401
    assert db.scalar(select(func.count()).select_from(User)) == 0
    assert client.get("/api/v1/auth/session").status_code == 401


def test_widget_verify_is_disabled_outside_widget_mode(client) -> None:
    response = client.post(
        "/api/v1/auth/otp/widget/verify", json={"access_token": "widget-access-token"}
    )
    assert response.status_code == 409


def test_widget_verify_fails_loudly_when_credentials_are_missing(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A half-configured widget must never fall back to logging OTPs."""
    _widget_mode(
        monkeypatch,
        msg91_auth_key="",
        msg91_widget_id="",
        msg91_widget_token="",
    )

    response = client.post(
        "/api/v1/auth/otp/widget/verify", json={"access_token": "widget-access-token"}
    )

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]
