"""LLM provider interface.

Everything the LLM is used for (simplify, translate, later chat) goes through
``LLMProvider``. Ships with:

- ``GeminiProvider`` (default per AGENTS.md 18.3): Gemini Flash free tier via
  plain ``httpx``. Selected with ``LLM_PROVIDER=gemini`` (the default) plus
  ``GEMINI_API_KEY``. Without a key the factory falls back to the mock
  provider so the app never crashes.
- ``MockProvider`` (tests and offline development): deterministic output built
  from the scheme record itself. No network, no cost.

The provider is the ONLY component allowed to talk to a model. It receives the
public scheme record (never user profile data, see AGENTS.md 9) and must
return strict JSON, validated here before any caller can use it.
"""

from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.services.llm.base import (
    ChatRequest,
    LLMError,
    LLMProvider,
    SimplificationRequest,
    SimplifiedContent,
)
from app.services.llm.claude import ClaudeProvider
from app.services.llm.gemini import GeminiProvider
from app.services.llm.mock import MockProvider

__all__ = [
    "ChatRequest",
    "ClaudeProvider",
    "GeminiProvider",
    "LLMError",
    "LLMProvider",
    "MockProvider",
    "SimplificationRequest",
    "SimplifiedContent",
    "get_chat_provider",
    "get_llm_provider",
]


def get_llm_provider() -> LLMProvider:
    """Build the configured provider.

    ``LLM_PROVIDER=gemini`` without ``GEMINI_API_KEY`` degrades to the mock
    provider with a warning instead of crashing the request path; scheme
    text then comes from the admin-written English fallback path.
    """
    settings = get_settings()
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            import logging

            logging.getLogger(__name__).warning(
                "llm_provider_falling_back_to_mock",
                extra={"reason": "GEMINI_API_KEY is not set"},
            )
            return MockProvider()
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    raise LLMError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")


def get_chat_provider() -> Any:
    """The provider behind the assistant.

    Phase 6 prompt: the chat runs on the Claude API; ``llm_provider`` stays
    the default for simplify/translate. ``LLM_PROVIDER=claude`` needs
    ANTHROPIC_API_KEY (degrading to the mock otherwise), any other value
    reuses the translate provider.
    """
    settings = get_settings()
    if settings.llm_provider == "claude":
        if not settings.anthropic_api_key:
            import logging

            logging.getLogger(__name__).warning(
                "chat_provider_falling_back_to_mock",
                extra={"reason": "ANTHROPIC_API_KEY is not set"},
            )
            return MockProvider()
        return ClaudeProvider(settings.anthropic_api_key, settings.anthropic_model)
    return get_llm_provider()

