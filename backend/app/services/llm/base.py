"""Provider-agnostic LLM types and protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """The provider failed to produce a valid simplification."""


@dataclass(frozen=True)
class SimplificationRequest:
    """What an LLM may see: public scheme text only.

    Never include user profile data here: free-tier models may retain
    prompts, so we send exactly the verified, public scheme record.
    """

    scheme: dict[str, Any]
    language: str  # target language code of the six app languages


@dataclass(frozen=True)
class SimplifiedContent:
    """Validated strict-JSON output of ``simplify_and_translate``."""

    simple_title: str
    simple_description: str
    simple_benefits: list[str]
    simple_steps: list[str]
    model_name: str | None = None
    fallback: bool = False  # True when a provider fell back to admin text
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class ChatRequest:
    """A grounded chat turn.

    ``system`` carries the assistant rules; ``records`` carries ONLY the
    retrieved scheme/disaster records the model may cite; ``history`` is the
    short recent transcript; ``user_message`` is the current question.
    """

    system: str
    records: str
    history: list[dict[str, str]]
    user_message: str


@runtime_checkable
class LLMProvider(Protocol):
    """Implementations turn a verified scheme record into simple text."""

    @property
    def name(self) -> str: ...  # pragma: no cover - trivial

    def simplify_and_translate(
        self, request: SimplificationRequest
    ) -> SimplifiedContent: ...  # pragma: no cover - trivial

    def chat(self, request: ChatRequest) -> str: ...  # pragma: no cover - trivial
