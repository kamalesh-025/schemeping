"""Scheme detail endpoint: translation generation/caching, deterministic
why-qualify wording, person handling, and draft hiding."""

from __future__ import annotations

from datetime import date, timedelta

from app.models.enums import SchemeStatus
from app.models.family import FamilyMember
from app.models.user import User
from app.services.llm import mock as mock_module
from app.services.schemes import SchemeNotFoundError, load_published_scheme
from fastapi.testclient import TestClient
from sqlalchemy import select as sa_select

from tests.test_translation_service import make_scheme

_PROFILE = {
    "name": "Lakshmi",
    "dob": date.fromisoformat("1985-06-15"),
    "gender": "female",
    "occupation": "farmer",
    "annual_income": 180000,
    "education": "secondary",
    "marital_status": "married",
    "state": "Tamil Nadu",
    "district": "Erode",
    "locality": "Perundurai",
    "pincode": "638052",
    "language": "en",
    "data_processing_consent": True,
    "whatsapp_opt_in": False,
}


def current_user_id(db) -> int:
    user = db.scalar(sa_select(User).where(User.mobile == "9876543210"))
    assert user is not None
    return int(user.id)


def complete_profile(db) -> None:
    user = db.scalar(sa_select(User).where(User.mobile == "9876543210"))
    assert user is not None
    for key, value in _PROFILE.items():
        setattr(
            user,
            "consent_data_processing" if key == "data_processing_consent" else (
                "consent_whatsapp" if key == "whatsapp_opt_in" else key
            ),
            value,
        )
    db.commit()


def test_detail_generates_then_serves_cached_translation(logged_in_client: TestClient, db):
    scheme = make_scheme(db)
    complete_profile(db)
    mock_module.clear_calls()

    first = logged_in_client.get(f"/api/v1/schemes/{scheme.id}", params={"lang": "ta"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["translation"]["simple_title"] == "[ta] A test scheme"
    assert body["translation"]["cached"] is False
    assert mock_module.recorded_calls() == [("detail-test-scheme", "ta")]

    # Deterministic engine wording, never produced by the LLM.
    assert any("You qualify" in line for line in body["why_qualify"])
    assert body["eligibility_status"] == "eligible"

    second = logged_in_client.get(f"/api/v1/schemes/{scheme.id}", params={"lang": "ta"})
    assert second.status_code == 200
    assert second.json()["translation"]["cached"] is True
    assert mock_module.recorded_calls() == [("detail-test-scheme", "ta")]


def test_detail_separate_language_is_new_generation(logged_in_client: TestClient, db):
    scheme = make_scheme(db)
    complete_profile(db)
    mock_module.clear_calls()

    logged_in_client.get(f"/api/v1/schemes/{scheme.id}", params={"lang": "en"})
    hindi = logged_in_client.get(f"/api/v1/schemes/{scheme.id}", params={"lang": "hi"})
    assert hindi.status_code == 200
    assert hindi.json()["translation"]["simple_title"] == "[hi] A test scheme"
    assert len(mock_module.recorded_calls()) == 2


def test_detail_includes_documents_steps_and_meta(logged_in_client: TestClient, db):
    scheme = make_scheme(db)
    complete_profile(db)

    response = logged_in_client.get(f"/api/v1/schemes/{scheme.id}")
    assert response.status_code == 200
    body = response.json()
    assert [doc["name"] for doc in body["required_documents"]] == ["Aadhaar card", "Student card"]
    assert [step["title"] for step in body["application_steps"]] == [
        "Get the documents",
        "Visit the office",
    ]
    assert body["department"] == "Test Department"
    assert body["days_remaining"] is not None and body["days_remaining"] >= 19
    assert body["last_verified_on"] == date.today().isoformat()
    assert body["source_url"] == "https://source.example/scheme"
    assert body["deadline"] == (date.today() + timedelta(days=20)).isoformat()


def test_detail_member_person_is_a_fresh_evaluation(logged_in_client: TestClient, db):
    scheme = make_scheme(db)
    complete_profile(db)

    created = logged_in_client.post(
        "/api/v1/family",
        json={"name": "Kannan", "relationship": "son", "dob": "2020-01-10"},
    )
    assert created.status_code == 201, created.text
    member_id = created.json()["id"]

    response = logged_in_client.get(
        f"/api/v1/schemes/{scheme.id}", params={"person": str(member_id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_status"] == "not_eligible"
    assert body["person"] == member_id
    assert any("Not eligible" in line for line in body["why_qualify"])
    assert any("Age must be >=" in line for line in body["why_qualify"])


def test_detail_foreign_member_is_404(logged_in_client: TestClient, db):
    scheme = make_scheme(db)
    complete_profile(db)

    other_user = User(
        mobile="9711111111",
        name="Other",
        state="Tamil Nadu",
        district="Madurai",
        pincode="625020",
        language="en",
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    member = FamilyMember(user_id=int(other_user.id), name="Secret", relationship="son")
    db.add(member)
    db.commit()
    db.refresh(member)

    response = logged_in_client.get(
        f"/api/v1/schemes/{scheme.id}", params={"person": str(member.id)}
    )
    assert response.status_code == 404


def test_detail_draft_is_hidden(logged_in_client: TestClient, db):
    draft = make_scheme(db)
    draft.status = SchemeStatus.DRAFT
    db.commit()

    response = logged_in_client.get(f"/api/v1/schemes/{draft.id}")
    assert response.status_code == 404


def test_detail_unknown_id_404(logged_in_client: TestClient):
    assert logged_in_client.get("/api/v1/schemes/999999").status_code == 404


def test_detail_requires_login(client: TestClient, db):
    scheme = make_scheme(db)
    response = client.get(f"/api/v1/schemes/{scheme.id}")
    assert response.status_code == 401


def test_publish_loader_hides_then_publishes(db):
    """Direct service check: drafts unreachable through load_published_scheme."""
    scheme = make_scheme(db)
    scheme.status = SchemeStatus.DRAFT
    db.commit()

    import pytest

    with pytest.raises(SchemeNotFoundError):
        load_published_scheme(db, int(scheme.id))

    scheme.status = SchemeStatus.PUBLISHED
    db.commit()
    db.refresh(scheme)
    assert load_published_scheme(db, int(scheme.id)).id == scheme.id
