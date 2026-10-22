"""Claude chat provider.

Phase 6 moves assistant conversations to the Claude API
(``/v1/messages``). Simplify/translate stay on the Phase 4 Gemini path:
this class implements only ``chat`` plus the provider book-keeping, and is
selected with ``LLM_PROVIDER=claude``.

The HTTP shape: POST with ``x-api-key`` + ``anthropic-version`` headers and
a ``system`` field; conversation history as alternating user/assistant
messages. Rate limits use the same backoff strategy as the Gemini client.
Tests inject ``transport`` (``httpx.MockTransport``).
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

import httpx

from app.services.llm.base import ChatRequest, LLMError

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
_RETRIES = 3
_TIMEOUT_SECONDS = 60.0
_BACKOFF_BASE = 0.5
_MAX_TOKENS = 1024


def _sleep_backoff(attempt: int) -> None:
    delay = min(_BACKOFF_BASE * (2 ** (attempt - 1)), 8) * random.uniform(0.5, 1.0)
    logger.info("llm_retry_scheduled", extra={"attempt": attempt, "delay_seconds": delay})
    time.sleep(delay)


class ClaudeProvider:
    """Grounded chat against ``POST /v1/messages``."""

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
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    def chat(self, request: ChatRequest) -> str:
        url = f"{self._base_url}/v1/messages"
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
        }
        messages = list(request.history)
        messages.append({"role": "user", "content": request.user_message})
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            "temperature": 0.2,
            "system": request.system + "\n\n" + request.records,
            "messages": messages,
        }

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
                    data = dict(response.json())
                    blocks = data.get("content", [])
                    text = "".join(
                        block.get("text", "")
                        for block in blocks
                        if isinstance(block, dict)
                    ).strip()
                    if not text:
                        raise LLMError("Claude response contained no text")
                    usage = data.get("usage", {}) or {}
                    logger.info(
                        "llm_usage",
                        extra={
                            "provider": self.name,
                            "model": self._model,
                            "prompt_tokens": usage.get("input_tokens"),
                            "completion_tokens": usage.get("output_tokens"),
                            "purpose": "chat",
                        },
                    )
                    return text
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    last_error = LLMError(
                        f"Claude returned HTTP {response.status_code} on attempt {attempt}"
                    )
                else:
                    raise LLMError(
                        f"Claude rejected the request: HTTP {response.status_code}"
                    )
            if attempt < _RETRIES:
                _sleep_backoff(attempt)
        raise LLMError(f"Claude call failed after {_RETRIES} attempts: {last_error}")
