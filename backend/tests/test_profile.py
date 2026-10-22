"""Profile validation, consent, and encryption at rest."""

from __future__ import annotations

import pytest
from sqlalchemy import text

VALID_PROFILE = {
    "name": "Lakshmi Narayanan",
    "dob": "1985-06-15",
    "gender": "female",
    "occupation": "farmer",
    "annual_income": 180000,
    "education": "secondary",
    "marital_status": "married",
    "state": "Tamil Nadu",
    "district": "Madurai",
    "locality": "Thiruparankundram",
    "pincode": "625005",
    "language": "ta",
    "data_processing_consent": True,
    "whatsapp_opt_in": True,
}


def test_profile_requires_authentication(client) -> None:
    assert client.put("/api/v1/me", json=VALID_PROFILE).status_code == 401
    assert client.get("/api/v1/me").status_code == 401


def test_full_profile_round_trip(logged_in_client) -> None:
    response = logged_in_client.put("/api/v1/me", json=VALID_PROFILE)
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["name"] == "Lakshmi Narayanan"
    assert body["district"] == "Madurai"
    assert body["language"] == "ta"
    assert body["profile_complete"] is True
    assert body["consent_data_processing"] is True
    assert body["consent_whatsapp"] is True
    assert body["consented_at"] is not None
    assert body["is_senior"] is False
    assert body["age"] is not None

    fetched = logged_in_client.get("/api/v1/me").json()
    assert fetched["annual_income"] == 180000


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("pincode", "0123"),
        ("pincode", "12345a"),
        ("pincode", "012345"),
        ("annual_income", -1),
        ("state", "Atlantis"),
        ("district", "Nowhere"),
        ("dob", "2099-01-01"),
        ("dob", "1899-12-31"),
        ("name", "X"),
    ],
)
def test_invalid_profile_values_are_rejected(logged_in_client, field, value) -> None:
    payload = {**VALID_PROFILE, field: value}
    response = logged_in_client.put("/api/v1/me", json=payload)
    assert response.status_code == 422


def test_district_must_belong_to_the_state(logged_in_client) -> None:
    payload = {**VALID_PROFILE, "state": "Kerala", "district": "Madurai"}
    # Kerala has no district list yet, so any district is accepted there.
    assert logged_in_client.put("/api/v1/me", json=payload).status_code == 200

    payload = {**VALID_PROFILE, "state": "Tamil Nadu", "district": "Kollam"}
    assert logged_in_client.put("/api/v1/me", json=payload).status_code == 422


def test_profile_is_incomplete_until_required_fields_are_set(logged_in_client) -> None:
    assert logged_in_client.get("/api/v1/me").json()["profile_complete"] is False
    logged_in_client.put("/api/v1/me", json=VALID_PROFILE)
    assert logged_in_client.get("/api/v1/me").json()["profile_complete"] is True


def test_sensitive_fields_are_encrypted_at_rest(logged_in_client, db) -> None:
    logged_in_client.put("/api/v1/me", json=VALID_PROFILE)

    raw = db.execute(
        text("SELECT dob, gender, annual_income FROM users LIMIT 1")
    ).one()

    assert b"1985-06-15" not in raw[0].encode()
    assert b"180000" not in raw[2].encode()
    assert raw[0].startswith("gAAAAA")  # Fernet token prefix

    # And the API still returns the plaintext to the owner.
    body = logged_in_client.get("/api/v1/me").json()
    assert body["dob"] == "1985-06-15"
    assert body["annual_income"] == 180000


def test_whatsapp_opt_out_records_a_timestamp(logged_in_client) -> None:
    logged_in_client.put("/api/v1/me", json=VALID_PROFILE)

    response = logged_in_client.patch(
        "/api/v1/me/consent/whatsapp", json={"whatsapp_opt_in": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["whatsapp_opt_in"] is False
    assert body["whatsapp_opted_out_at"] is not None

    # Opting back in clears the opt-out timestamp.
    response = logged_in_client.patch(
        "/api/v1/me/consent/whatsapp", json={"whatsapp_opt_in": True}
    )
    assert response.json()["whatsapp_opted_out_at"] is None


def test_consent_can_be_read_separately(logged_in_client) -> None:
    logged_in_client.put("/api/v1/me", json=VALID_PROFILE)
    body = logged_in_client.get("/api/v1/me/consent").json()
    assert body == {
        "data_processing": True,
        "whatsapp_opt_in": True,
        "consented_at": body["consented_at"],
        "whatsapp_opted_out_at": None,
        "policy_version": "2026-10-01",
    }


def test_deleting_an_account_requires_confirmation(logged_in_client) -> None:
    response = logged_in_client.request(
        "DELETE", "/api/v1/me", json={"confirm": "yes"}
    )
    assert response.status_code == 422
