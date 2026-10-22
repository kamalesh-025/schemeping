"""OTP lifecycle: hashing, expiry, rate limits, and lockout."""

from __future__ import annotations

from datetime import timedelta

import pytest
from app.core.config import get_settings
from app.core.security import hash_otp
from app.core.time import utcnow
from app.models.otp import OtpRequest
from app.services import otp as otp_service
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _otp_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tests exercise the OTP flow; password is the product default."""
    monkeypatch.setattr(get_settings(), "auth_mode", "otp", raising=False)


def _request(client, mobile: str = "9876543210"):
    return client.post("/api/v1/auth/otp/request", json={"mobile": mobile})


def _verify(client, code: str, mobile: str = "9876543210"):
    return client.post(
        "/api/v1/auth/otp/verify", json={"mobile": mobile, "otp": code}
    )


def test_otp_is_never_stored_in_plaintext(client, otp_provider, db) -> None:
    response = _request(client)
    assert response.status_code == 200

    code = otp_provider.last_code
    record = db.scalars(select(OtpRequest)).one()

    assert record.otp_hash != code
    assert record.otp_hash == hash_otp("9876543210", code)
    assert code not in record.otp_hash


def test_otp_request_response_does_not_leak_the_code(client) -> None:
    response = _request(client)
    assert response.status_code == 200
    body = response.json()
    assert "otp" not in body
    assert "code" not in body
    assert set(body) == {"message", "expires_in_seconds", "resend_after_seconds"}


def test_mobile_number_is_normalised(client, otp_provider, db) -> None:
    response = _request(client, "+91 98765 43210")
    assert response.status_code == 200

    record = db.scalars(select(OtpRequest)).one()
    assert record.mobile == "9876543210"
    assert otp_provider.sent[-1][0] == "9876543210"


@pytest.mark.parametrize(
    "mobile", ["12345", "1234567890", "98765", "abcdefghij", "+1 555 0100"]
)
def test_invalid_mobile_numbers_are_rejected(client, mobile: str) -> None:
    response = _request(client, mobile)
    assert response.status_code == 422


def test_third_request_in_window_is_allowed_and_fourth_is_rate_limited(
    client, otp_provider
) -> None:
    for _ in range(3):
        assert _request(client).status_code == 200

    response = _request(client)
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0
    assert len(otp_provider.sent) == 3


def test_rate_limit_is_per_mobile(client) -> None:
    for _ in range(3):
        _request(client, "9876543210")

    assert _request(client, "9876543210").status_code == 429
    assert _request(client, "9123456780").status_code == 200


def test_rate_limit_is_per_ip(client) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.otp_max_requests_per_ip
    object.__setattr__(settings, "otp_max_requests_per_ip", 2)
    try:
        assert _request(client, "9876543210").status_code == 200
        assert _request(client, "9876543211").status_code == 200
        # Different mobiles, same TestClient IP: blocked by the IP limit.
        assert _request(client, "9876543212").status_code == 429
    finally:
        object.__setattr__(settings, "otp_max_requests_per_ip", original)


def test_expired_otp_is_rejected(client, otp_provider, db) -> None:
    _request(client)
    record = db.scalars(select(OtpRequest)).one()
    record.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    response = _verify(client, otp_provider.last_code)
    assert response.status_code == 410
    assert "expired" in response.json()["detail"].lower()


def test_wrong_otp_counts_attempts_and_locks_out(client, otp_provider, db) -> None:
    _request(client)
    wrong = "000000" if otp_provider.last_code != "000000" else "111111"

    for attempt in range(1, 5):
        response = _verify(client, wrong)
        assert response.status_code == 400
        # End the read transaction so MySQL's REPEATABLE READ snapshot is
        # refreshed and the committed attempt count is visible.
        db.rollback()
        record = db.scalars(select(OtpRequest)).one()
        assert record.attempts == attempt

    # Fifth wrong attempt locks the OTP.
    response = _verify(client, wrong)
    assert response.status_code == 400

    # Even the correct code is now refused.
    response = _verify(client, otp_provider.last_code)
    assert response.status_code == 429
    assert "too many" in response.json()["detail"].lower()


def test_correct_otp_consumes_it(client, otp_provider, db) -> None:
    _request(client)
    code = otp_provider.last_code

    assert _verify(client, code).status_code == 200

    record = db.scalars(select(OtpRequest)).one()
    assert record.consumed_at is not None

    # Replaying the same code fails.
    assert _verify(client, code).status_code == 400


def test_new_otp_invalidates_the_previous_one(client, otp_provider) -> None:
    _request(client)
    first_code = otp_provider.last_code
    _request(client)
    second_code = otp_provider.last_code

    assert first_code != second_code
    assert _verify(client, first_code).status_code == 400
    assert _verify(client, second_code).status_code == 200


def test_otp_verification_creates_the_account_once(client, otp_provider, db) -> None:
    from app.models.user import User

    for _ in range(2):
        _request(client)
        assert _verify(client, otp_provider.last_code).status_code == 200

    users = db.scalars(select(User).where(User.mobile == "9876543210")).all()
    assert len(users) == 1
    assert users[0].mobile_verified_at is not None


def test_verify_without_a_request_is_rejected(client) -> None:
    response = _verify(client, "123456", "9000000001")
    assert response.status_code == 400


def test_request_otp_uses_the_injected_provider(otp_provider) -> None:
    assert otp_provider.sent == []
    assert otp_service.SMS_SENT_MESSAGE.startswith("If this number")
