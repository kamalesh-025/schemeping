"""Gemini Flash provider (the default) via plain httpx.

Free tier notes (AGENTS.md 18.3): prompts carry only public scheme text;
responses are requested as strict JSON. Rate limits are handled with
exponential backoff + jitter; a hard failure raises ``LLMError`` and the
calling service falls back to the admin-written English text.

Tests inject ``transport`` (``httpx.MockTransport``) so no real network is
ever touched.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from app.services.llm.base import (
    ChatRequest,
    LLMError,
    SimplificationRequest,
    SimplifiedContent,
)
from app.services.llm.prompt import build_messages, parse_output

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# Flash-Lite: the free tier of the Flash family, and the fastest to answer a
# chat turn. The "latest" alias keeps working when Google rolls the model.
_DEFAULT_MODEL_FALLBACK = "gemini-flash-lite-latest"
_RETRIES = 3
_TIMEOUT_SECONDS = 30.0
_BACKOFF_BASE = 0.5  # seconds; doubles per attempt, multiplied by jitter

_HTTP_STATUS_TOO_MANY_REQUESTS = 429


def _sleep_backoff(attempt: int) -> None:
    """Exponential backoff with jitter: attempt 1 -> ~0.5s, 2 -> ~1s, 3 -> ~2s."""
    delay = min(_BACKOFF_BASE * (2 ** (attempt - 1)), 8) * random.uniform(0.5, 1.0)
    logger.info("llm_retry_scheduled", extra={"attempt": attempt, "delay_seconds": delay})
    time.sleep(delay)


def _chat_contents(
    history: list[dict[str, str]], user_message: str
) -> list[dict[str, Any]]:
    """Gemini conversation contents.

    Gemini calls the model turn ``model`` (not ``assistant``) and rejects a
    transcript that starts with a model turn. Consecutive turns with the same
    role are merged so the transcript stays valid however it was stored.
    """
    contents: list[dict[str, Any]] = []
    for turn in history:
        role = "model" if turn.get("role") in {"assistant", "model"} else "user"
        text = str(turn.get("content") or "").strip()
        if not text:
            continue
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "Hello"}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    return contents


class GeminiProvider:
    """``simplify_and_translate`` against the Gemini generateContent API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """One POST with retries; returns the parsed response dictionary."""
        url = f"{self._base_url}/models/{self._model}:generateContent"
        headers = {"x-goog-api-key": self._api_key}
        last_error: Exception | None = None
        for attempt in range(1, _RETRIES + 1):
            try:
                with httpx.Client(
                    timeout=_TIMEOUT_SECONDS, transport=self._transport
                ) as client:
                    response = client.post(url, headers=headers, json=body)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code < 400:
                    return dict(response.json())
                if response.status_code == _HTTP_STATUS_TOO_MANY_REQUESTS or (
                    500 <= response.status_code < 600
                ):
                    last_error = LLMError(
                        f"Gemini returned HTTP {response.status_code} on attempt {attempt}"
                    )
                else:
                    detail = ""
                    try:
                        error_body = response.json().get("error", {})
                        detail = str(error_body.get("message") or "")[:300]
                    except (ValueError, AttributeError):
                        detail = response.text[:300]
                    logger.error(
                        "gemini_rejected_request",
                        extra={"status_code": response.status_code, "detail": detail},
                    )
                    # Keep the provider's own words: "model no longer
                    # available", "API key invalid" and "quota exceeded" all
                    # need different fixes, and the status code alone hides
                    # which one happened.
                    raise LLMError(
                        "Gemini rejected the request: "
                        f"HTTP {response.status_code} {detail}".rstrip()
                    )
            if attempt < _RETRIES:
                _sleep_backoff(attempt)
        raise LLMError(f"Gemini call failed after {_RETRIES} attempts: {last_error}")

    def _post_with_fallback(self, body: dict[str, Any]) -> dict[str, Any]:
        """Retry once with the fallback model when the configured one is gone.

        Google retires dated models for new keys (HTTP 404: "no longer
        available to new users"). A deployment that pinned a model must not
        break silently: switch to the free-tier alias and say so in the logs.
        """
        try:
            return self._post(body)
        except LLMError as exc:
            if "HTTP 404" not in str(exc) or self._model == _DEFAULT_MODEL_FALLBACK:
                raise
            logger.warning(
                "llm_model_unavailable_using_fallback",
                extra={"model": self._model, "fallback": _DEFAULT_MODEL_FALLBACK},
            )
            self._model = _DEFAULT_MODEL_FALLBACK
            return self._post(body)

    def simplify_and_translate(
        self, request: SimplificationRequest
    ) -> SimplifiedContent:
        messages = build_messages(request.scheme, request.language)
        body: dict[str, Any] = {
            "system_instruction": {"parts": [{"text": messages[0]["content"]}]},
            "contents": [
                {"role": "user", "parts": [{"text": messages[1]["content"]}]}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }

        data = self._post_with_fallback(body)

        text_parts = [
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in (candidate.get("content", {}) or {}).get("parts", [])
        ]
        raw = "".join(text_parts).strip()
        if not raw:
            raise LLMError("Gemini response contained no text")

        try:
            payload = parse_output(raw)
        except ValueError as exc:
            raise LLMError(f"Gemini output failed validation: {exc}") from exc

        usage = data.get("usageMetadata", {}) or {}
        prompt_tokens = usage.get("promptTokenCount")
        completion_tokens = usage.get("candidatesTokenCount")
        total_tokens = usage.get("totalTokenCount")
        logger.info(
            "llm_usage",
            extra={
                "provider": self.name,
                "model": self._model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "language": request.language,
            },
        )

        return SimplifiedContent(
            simple_title=payload["simple_title"],
            simple_description=payload["simple_description"],
            simple_benefits=payload["simple_benefits"],
            simple_steps=payload["simple_steps"],
            model_name=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def chat(self, request: ChatRequest) -> str:
        """Free-form conversational answer (no JSON mode needed).

        The retrieved records are DATA for the model and must travel with the
        system instruction; otherwise Gemini would answer without any context.
        """
        body: dict[str, Any] = {
            "system_instruction": {
                "parts": [{"text": request.system + "\n\n" + request.records}]
            },
            "contents": _chat_contents(request.history, request.user_message),
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.95,
                "maxOutputTokens": 1200,
            },
        }
        data = self._post_with_fallback(body)
        text_parts = [
            part.get("text", "")
            for candidate in data.get("candidates", [])
            for part in (candidate.get("content", {}) or {}).get("parts", [])
        ]
        raw = "".join(text_parts).strip()
        if not raw:
            blocked = (data.get("promptFeedback", {}) or {}).get("blockReason")
            raise LLMError(
                f"Gemini response contained no text (blockReason={blocked})"
            )
        usage = data.get("usageMetadata", {}) or {}
        logger.info(
            "llm_usage",
            extra={
                "provider": self.name,
                "model": self._model,
                "prompt_tokens": usage.get("promptTokenCount"),
                "completion_tokens": usage.get("candidatesTokenCount"),
                "total_tokens": usage.get("totalTokenCount"),
                "purpose": "chat",
            },
        )
        return raw
