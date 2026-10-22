"""Tests for the LLM provider layer: mock determinism, Gemini retries,
strict JSON validation, and usage logging — all without any real network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.services.llm import (
    ChatRequest,
    GeminiProvider,
    LLMError,
    MockProvider,
    SimplificationRequest,
    get_llm_provider,
)
from app.services.llm import mock as mock_module
from app.services.llm.prompt import build_messages, parse_output, scheme_payload

SCHEME = {
    "slug": "test-scheme",
    "name": "A test scheme",
    "benefit_summary": "Gives students money for books.",
    "benefit_amount": "₹1,000 per year",
    "benefits": ["Books money", "Tuition help"],
    "steps": ["Collect documents", "Visit the office"],
    "department": "Test Department",
}

REQUEST = SimplificationRequest(scheme=SCHEME, language="ta")


# ------------------------------------------------------------------ mock


def test_mock_provider_is_deterministic():
    provider = MockProvider()
    first = provider.simplify_and_translate(REQUEST)
    second = provider.simplify_and_translate(REQUEST)
    assert first.simple_title == second.simple_title == "[ta] A test scheme"
    assert first.simple_description.startswith("[ta] ")
    assert first.fallback is False
    assert first.simple_benefits == ["Books money", "Tuition help"]
    assert first.simple_steps == ["Collect documents", "Visit the office"]


def test_mock_provider_records_calls():
    mock_module.clear_calls()
    provider = MockProvider()
    provider.simplify_and_translate(REQUEST)
    provider.simplify_and_translate(SimplificationRequest(scheme=SCHEME, language="en"))
    calls = mock_module.recorded_calls()
    assert calls[-2:] == [("test-scheme", "ta"), ("test-scheme", "en")]


# ------------------------------------------------------------------ prompts


def test_prompt_contains_only_public_fields_and_language_rule():
    messages = build_messages(SCHEME, "ta")
    system = messages[0]["content"]
    user = messages[1]["content"]
    assert "Tamil" in system
    assert "Add no new schemes, amounts" in system
    payload = json.loads(user.split("Scheme record: ", 1)[1])
    assert set(payload) <= set(scheme_payload(SCHEME))
    assert payload["name"] == "A test scheme"


def test_parse_output_accepts_clean_and_fenced_json():
    clean = json.dumps(
        {
            "simple_title": "t",
            "simple_description": "d",
            "simple_benefits": ["b"],
            "simple_steps": ["s"],
        }
    )
    assert parse_output(clean)["simple_title"] == "t"
    fenced = f"```json\n{clean}\n```"
    assert parse_output(fenced)["simple_steps"] == ["s"]


@pytest.mark.parametrize(
    "bad",
    [
        "not json at all",
        "[]",
        json.dumps(
            {
                "simple_title": "",
                "simple_description": "d",
                "simple_benefits": [],
                "simple_steps": [],
            }
        ),
        json.dumps(
            {
                "simple_title": "t",
                "simple_description": "d",
                "simple_benefits": [""],
                "simple_steps": [],
            }
        ),
        json.dumps({"simple_title": "t", "simple_description": "d", "simple_benefits": ["b"]}),
    ],
)
def test_parse_output_rejects_invalid_payloads(bad):
    with pytest.raises(ValueError):
        parse_output(bad)


# ------------------------------------------------------------------ gemini


def _gemini_with_response(responder) -> GeminiProvider:
    transport = httpx.MockTransport(responder)
    return GeminiProvider(
        "key", "gemini-2.5-flash", base_url="https://mock.local", transport=transport
    )


VALID_BODY = json.dumps(
    {
        "simple_title": "[ta] title",
        "simple_description": "[ta] what it is",
        "simple_benefits": ["one", "two"],
        "simple_steps": ["step one"],
    }
)


def _fake_usage_response(content: str, status_code: int = 200) -> httpx.Response:
    if status_code != 200:
        return httpx.Response(
            status_code,
            request=httpx.Request(
                "POST", "https://mock.local/models/gemini-2.5-flash:generateContent"
            ),
        )
    return httpx.Response(
        200,
        request=httpx.Request("POST", "https://mock.local/models/gemini-2.5-flash:generateContent"),
        json={
            "candidates": [{"content": {"parts": [{"text": content}]}}],
            "usageMetadata": {
                "promptTokenCount": 120,
                "candidatesTokenCount": 180,
                "totalTokenCount": 300,
            },
        },
    )


def test_gemini_success_reports_usage(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    provider = _gemini_with_response(lambda request: _fake_usage_response(VALID_BODY))
    content = provider.simplify_and_translate(REQUEST)
    assert content.simple_title == "[ta] title"
    assert content.model_name == "gemini-2.5-flash"
    assert content.total_tokens == 300
    assert content.prompt_tokens == 120


def test_gemini_recovers_on_server_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    calls = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return _fake_usage_response("ignored", status_code=503)
        return _fake_usage_response(VALID_BODY)

    provider = _gemini_with_response(responder)
    content = provider.simplify_and_translate(REQUEST)
    assert calls["count"] == 2
    assert content.simple_steps == ["step one"]


def test_gemini_gives_up_after_retries(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    provider = _gemini_with_response(
        lambda request: _fake_usage_response("ignored", status_code=503)
    )
    with pytest.raises(LLMError, match="after 3 attempts"):
        provider.simplify_and_translate(REQUEST)


def test_gemini_client_error_is_not_retried(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    calls = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return _fake_usage_response("ignored", status_code=400)

    provider = _gemini_with_response(responder)
    with pytest.raises(LLMError, match="HTTP 400"):
        provider.simplify_and_translate(REQUEST)
    assert calls["count"] == 1  # no retries for a 4xx client error


def test_gemini_uses_the_fallback_model_when_the_pinned_one_is_retired(
    monkeypatch: pytest.MonkeyPatch,
):
    """Google retires dated models; a pinned model must not break the app.

    The first call (to the retired model) answers 404, so the provider switches
    to the free-tier alias and retries once instead of failing the user.
    """
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    seen: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "gemini-2.5-flash" in str(request.url):
            return httpx.Response(404, request=request, json={"error": {"code": 404}})
        return _fake_usage_response(VALID_BODY)

    provider = _gemini_with_response(responder)
    content = provider.simplify_and_translate(REQUEST)

    assert content.simple_title == "[ta] title"
    assert len(seen) == 2
    assert "gemini-flash-lite-latest" in seen[1]


def test_gemini_invalid_model_json_is_an_llm_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    provider = _gemini_with_response(
        lambda request: _fake_usage_response("Here is my answer: no json")
    )
    with pytest.raises(LLMError, match="failed validation"):
        provider.simplify_and_translate(REQUEST)


def test_gemini_rate_limit_recovers(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app.services.llm.gemini._sleep_backoff", lambda attempt: None)
    calls = {"count": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return _fake_usage_response("ignored", status_code=429)
        return _fake_usage_response(VALID_BODY)

    provider = _gemini_with_response(responder)
    assert provider.simplify_and_translate(REQUEST).simple_description == "[ta] what it is"


def test_gemini_chat_sends_records_and_uses_model_role():
    """The assistant must receive the records, and Gemini needs 'model' turns."""
    seen: dict[str, Any] = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return _fake_usage_response("Hello! How can I help?")

    provider = _gemini_with_response(responder)
    reply = provider.chat(
        ChatRequest(
            system="SYSTEM RULES",
            records="SCHEME RECORDS: []",
            history=[{"role": "assistant", "content": "Welcome"}],
            user_message="What can I get?",
        )
    )

    assert reply == "Hello! How can I help?"
    body: dict[str, Any] = seen["body"]
    system_text = body["system_instruction"]["parts"][0]["text"]
    assert "SYSTEM RULES" in system_text
    assert "SCHEME RECORDS" in system_text
    roles = [turn["role"] for turn in body["contents"]]
    assert roles == ["user", "model", "user"]
    assert body["generationConfig"]["temperature"] == 0.7


# ------------------------------------------------------------------ factory


@pytest.fixture
def llm_settings(monkeypatch: pytest.MonkeyPatch):
    """A stand-in for the cached settings object seen by the LLM factory."""

    from types import SimpleNamespace

    import app.services.llm as llm_package

    fake = SimpleNamespace(
        llm_provider="gemini",
        gemini_api_key="",
        gemini_model="gemini-2.5-flash",
    )
    monkeypatch.setattr(llm_package, "get_settings", lambda: fake)
    return fake


def test_factory_returns_mock_without_api_key(llm_settings):
    llm_settings.llm_provider = "gemini"
    llm_settings.gemini_api_key = ""
    assert get_llm_provider().name == "mock"


def test_factory_builds_gemini_with_key(llm_settings):
    llm_settings.llm_provider = "gemini"
    llm_settings.gemini_api_key = "k"
    provider = get_llm_provider()
    assert isinstance(provider, GeminiProvider)


def test_factory_mock_selection(llm_settings):
    llm_settings.llm_provider = "mock"
    assert get_llm_provider().name == "mock"


def test_factory_unknown_provider(llm_settings):
    llm_settings.llm_provider = "notreal"
    with pytest.raises(LLMError, match="Unknown LLM_PROVIDER"):
        get_llm_provider()
