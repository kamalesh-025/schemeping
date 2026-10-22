"""Translation cache behaviour: hit, miss, invalidation, and fallback."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from app.models.enums import SchemeStatus
from app.models.scheme import Scheme, SchemeTranslation
from app.services.llm import (
    LLMError,
    MockProvider,
    SimplificationRequest,
    SimplifiedContent,
)
from app.services.llm import mock as mock_module
from app.services.translations import content_hash, get_or_generate_translation
from sqlalchemy import select

from tests.conftest import make_completed_profile


class FailingProvider(MockProvider):
    """A provider that always fails, forcing the admin-text fallback."""

    @property
    def name(self) -> str:
        return "failing-mock"

    def simplify_and_translate(self, request: SimplificationRequest) -> SimplifiedContent:
        raise LLMError("outline overload; mock failure")


def make_scheme(db, **overrides) -> Scheme:
    values: dict = {
        "slug": "detail-test-scheme",
        "name": "A test scheme",
        "department": "Test Department",
        "level": "state",
        "state": "Tamil Nadu",
        "category": "education",
        "scope": "individual",
        "benefit_summary": "Gives students money for books.",
        "benefit_amount": "₹1,200 per year",
        "benefit_type": "cash",
        "eligibility_rules": {
            "applies_to": "individual",
            "rules": {
                "all": [
                    {"field": "age", "op": ">=", "value": 30},
                    {"field": "state", "op": "==", "value": "Tamil Nadu"},
                ]
            },
        },
        "required_documents": [
            {"name": "Aadhaar card", "notes": "Copy"},
            {"name": "Student card", "notes": None},
        ],
        "application_steps": [
            {"order": 1, "title": "Get the documents", "description": "Aadhaar and student card."},
            {"order": 2, "title": "Visit the office", "description": "The listed office."},
        ],
        "apply_url": "https://example.com/apply",
        "deadline": date.today() + timedelta(days=20),
        "priority": 50,
        "last_verified_on": date.today(),
        "source_url": "https://source.example/scheme",
    }
    values.update(overrides)
    scheme = Scheme(status=SchemeStatus.PUBLISHED, **values)
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    return scheme


@pytest.fixture
def mock_provider():
    return MockProvider()


def test_cache_miss_then_hit(db, mock_provider):
    scheme = make_scheme(db)
    mock_module.clear_calls()

    first = get_or_generate_translation(db, scheme, "ta", provider=mock_provider)
    assert first.cached is False
    assert first.fallback is False
    assert first.translation.simple_title == "[ta] A test scheme"
    assert first.translation.source_hash == content_hash(scheme)

    second = get_or_generate_translation(db, scheme, "ta", provider=mock_provider)
    assert second.cached is True
    assert mock_module.recorded_calls() == [("detail-test-scheme", "ta")]

    rows = db.scalars(select(SchemeTranslation)).all()
    assert len(rows) == 1


def test_other_language_is_a_separate_cache_entry(db, mock_provider):
    scheme = make_scheme(db)
    mock_module.clear_calls()
    get_or_generate_translation(db, scheme, "en", provider=mock_provider)
    get_or_generate_translation(db, scheme, "ta", provider=mock_provider)
    rows = db.scalars(select(SchemeTranslation)).all()
    assert {row.language for row in rows} == {"en", "ta"}
    assert len(mock_module.recorded_calls()) == 2


def test_content_change_invalidates_existing_translation(db, mock_provider):
    scheme = make_scheme(db)
    mock_module.clear_calls()
    get_or_generate_translation(db, scheme, "en", provider=mock_provider)

    scheme.benefit_amount = "₹5,000 per year"
    db.commit()

    result = get_or_generate_translation(db, scheme, "en", provider=mock_provider)
    assert result.cached is False
    assert result.translation.simple_description.startswith("[en] ")
    assert result.translation.source_hash == content_hash(scheme)
    assert len(mock_module.recorded_calls()) == 2


def test_provider_failure_falls_back_to_admin_text(db):
    scheme = make_scheme(db)
    failing = FailingProvider()

    result = get_or_generate_translation(db, scheme, "ta", provider=failing)
    assert result.fallback is True
    translation = result.translation
    assert translation.simple_title == "A test scheme"
    assert translation.simple_description == "Gives students money for books."
    assert translation.simple_benefits == ["₹1,200 per year", "Gives students money for books."]
    assert translation.simple_steps == ["Get the documents", "Visit the office"]
    assert translation.generated_by == "fallback"

    # A failing provider is still cached: no second call, no repeated failure.
    again = get_or_generate_translation(db, scheme, "ta", provider=failing)
    assert again.cached is True


def test_unknown_language_rejected(db, mock_provider):
    scheme = make_scheme(db)
    with pytest.raises(ValueError):
        get_or_generate_translation(db, scheme, "fr", provider=mock_provider)


def test_content_hash_stable_and_input_sensitive(db):
    scheme = make_scheme(db)
    assert content_hash(scheme) == content_hash(scheme)
    other = make_scheme(db, slug="other-scheme", name="Another test scheme")
    assert content_hash(scheme) != content_hash(other)


def test_user_profile_helper_still_reachable(db):
    user = make_completed_profile(db)
    assert user.name == "Lakshmi"
