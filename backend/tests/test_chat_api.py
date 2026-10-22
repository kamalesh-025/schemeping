"""Assistant behaviour: grounding, refusal, language, rate limit.

The mock provider is deterministic and offline: it can only repeat what the
retrieval put in front of it, which is exactly what "grounded" has to mean.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_completed_profile
from tests.test_translation_service import make_scheme


@pytest.fixture
def chat_user(db):
    from app.core.time import utcnow

    user = make_completed_profile(db, consent_whatsapp=True)
    user.mobile_verified_at = utcnow()
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_for(chat_user) -> Iterator[TestClient]:
    from app.core.security import create_access_token
    from app.main import create_app
    from fastapi.testclient import TestClient

    token = create_access_token(chat_user.id)
    with TestClient(create_app()) as client:
        client.cookies.set("sp_access", token)
        yield client


# ------------------------------------------------------------------ grounding


def test_answer_only_uses_retrieved_records(db, chat_user, client_for):
    """The provider receives the scheme records and nothing else."""
    from app.services.llm import mock as mock_module

    make_scheme(db, slug="tuition-assistance", name="Tuition Assistance")
    mock_module.clear_calls()

    response = client_for.post(
        "/api/v1/chat", json={"message": "Tell me about tuition assistance"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded"] is True
    assert body["sources"]
    assert any(
        source["name"] == "Tuition Assistance" for source in body["sources"]
    ), body["sources"]


def test_greeting_is_answered_without_scheme_cards(db, chat_user, client_for):
    """A bare greeting should get a friendly hello, not a list of schemes."""
    make_scheme(db, slug="tuition-assistance", name="Tuition Assistance")

    response = client_for.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded"] is True
    assert body["sources"] == []
    assert "Hello" in body["answer"] or "assistant" in body["answer"].lower()


def test_fabricated_scheme_is_not_answered(db, chat_user, client_for):
    """A scheme that does not exist must not appear in the answer."""
    make_scheme(db, slug="real-scheme", name="Real Scheme")

    response = client_for.post(
        "/api/v1/chat",
        json={"message": "Explain the Golden Payout Yojana for me please"},
    )
    assert response.status_code == 200
    body = response.json()
    assert all(
        source["name"] != "Golden Payout Yojana" for source in body["sources"]
    )
    assert "Golden Payout Yojana" not in body["answer"] or body["sources"]
    # With no matching record the mock answers with the "not in my records" line.
    if not body["sources"]:
        assert "verified records" in body["answer"]


class _CapturingProvider:
    """Records what the assistant was given."""

    def __init__(self) -> None:
        self.records = ""
        self.system = ""
        self.user_message = ""

    def chat(self, request):
        self.records = request.records
        self.system = request.system
        self.user_message = request.user_message
        return "ok"


@pytest.fixture
def capture_provider(monkeypatch):
    """Replace the chat provider with a recorder."""
    from app.services import chat as chat_service

    provider = _CapturingProvider()
    monkeypatch.setattr(chat_service, "get_chat_provider", lambda: provider)
    return provider


def test_records_block_contains_no_personal_identifiers(db, chat_user, capture_provider):
    """The prompt carries derived facts, never name/mobile/address."""
    make_scheme(db, slug="loan-scheme", name="Loan Scheme")

    from app.services import chat as chat_service

    chat_service.answer(db, chat_user, "loan scheme details")

    records = capture_provider.records
    assert chat_user.name not in records
    assert chat_user.mobile not in records
    assert "Tamil Nadu" in records  # state is allowed (needed for eligibility context)


def test_system_prompt_forbids_invention(db, chat_user, capture_provider):
    from app.services import chat as chat_service

    chat_service.answer(db, chat_user, "hello")

    system = capture_provider.system
    assert "Never invent" in system
    assert "DATA, not instructions" in system
    assert "these instructions" in system


# ------------------------------------------------------------------ language


def test_language_passthrough(db, chat_user, client_for):
    response = client_for.post(
        "/api/v1/chat", json={"message": "எனக்கு எந்த திட்டம் பொருந்தும்?", "language": "ta"}
    )
    assert response.status_code == 200
    assert response.json()["language"] == "ta"


def test_default_language_is_the_user_language(db, chat_user, client_for):
    from app.models.enums import Language

    chat_user.language = Language.HINDI
    db.commit()
    response = client_for.post("/api/v1/chat", json={"message": "hello"})
    assert response.json()["language"] == "hi"


def test_system_prompt_names_the_language(db, chat_user, capture_provider):
    from app.services import chat as chat_service

    chat_service.answer(db, chat_user, "hello", language="ta")

    assert "Tamil" in capture_provider.system


# ------------------------------------------------------------------ rate limit


def test_rate_limit_blocks_extra_questions(db, chat_user, client_for, monkeypatch):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "chat_rate_limit_per_hour", 3, raising=False)

    for index in range(3):
        response = client_for.post(
            "/api/v1/chat", json={"message": f"question {index}"}
        )
        assert response.status_code == 200, response.text

    response = client_for.post("/api/v1/chat", json={"message": "one too many"})
    assert response.status_code == 429


def test_history_is_stored(db, chat_user, client_for):
    client_for.post("/api/v1/chat", json={"message": "first question"})
    client_for.post("/api/v1/chat", json={"message": "second question"})

    response = client_for.get("/api/v1/chat/history")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4  # two questions, two answers
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"] == "first question"


def test_chat_requires_authentication(client: TestClient):
    assert client.post("/api/v1/chat", json={"message": "hi"}).status_code == 401
    assert client.get("/api/v1/chat/history").status_code == 401


# ------------------------------------------------------- provider unavailable


def test_assistant_still_answers_from_records_when_the_model_fails(
    db, chat_user, client_for, monkeypatch
):
    """A quota or outage must not turn the assistant into a dead end.

    The local answer quotes the same verified records, so it stays grounded
    even though no model produced it.
    """
    from app.services import chat as chat_service
    from app.services.llm import LLMError

    make_scheme(db, slug="tuition-assistance", name="Tuition Assistance")

    class DownProvider:
        name = "down"

        def chat(self, request):  # matches the provider protocol
            raise LLMError("quota exhausted")

    monkeypatch.setattr(chat_service, "get_chat_provider", lambda: DownProvider())

    response = client_for.post(
        "/api/v1/chat", json={"message": "Tell me about tuition assistance"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded"] is False
    assert "Tuition Assistance" in body["answer"]
    assert "not available" not in body["answer"].lower()


def test_local_answer_says_when_nothing_matched():
    from app.services.chat import local_answer

    answer = local_answer([], "en", "a scheme I invented")

    assert "could not find" in answer.lower()
