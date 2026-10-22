"""Deterministic mock provider for tests and offline development."""

from __future__ import annotations

import json
from typing import Any

from app.services.llm.base import (
    ChatRequest,
    SimplificationRequest,
    SimplifiedContent,
)

_CALLS: list[tuple[str, str]] = []


def recorded_calls() -> list[tuple[str, str]]:
    """(slug, language) pairs of every call, newest last. For cache tests."""
    return list(_CALLS)


def clear_calls() -> None:
    _CALLS.clear()


class MockProvider:
    """Deterministic offline simplifier built from the record itself.

    Same input, same output; never touches a network. Records its calls so
    the translation-cache tests can assert "second request: zero calls".
    """

    def __init__(self, model_name: str = "mock-simple") -> None:
        self._model = model_name

    @property
    def name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return self._model

    def simplify_and_translate(
        self, request: SimplificationRequest
    ) -> SimplifiedContent:
        scheme: dict[str, Any] = request.scheme
        _CALLS.append((str(scheme.get("slug")), request.language))
        title = str(scheme.get("name") or "Scheme")
        description = str(scheme.get("benefit_summary") or title)
        if scheme.get("benefits") is not None:
            benefits = [str(item) for item in scheme.get("benefits") or []]
        else:
            benefits = [
                str(item)
                for item in (scheme.get("benefit_amount"), scheme.get("benefit_summary"))
                if item
            ]
        if scheme.get("steps") is not None:
            steps = [str(item) for item in scheme.get("steps") or []]
        else:
            steps = [
                str(step.get("title", "")).strip()
                for step in (scheme.get("application_steps") or [])
                if step.get("title")
            ]
        return SimplifiedContent(
            simple_title=f"[{request.language}] {title}",
            simple_description=f"[{request.language}] {description}",
            simple_benefits=benefits,
            simple_steps=steps,
            model_name=self._model,
            prompt_tokens=len(request.scheme.get("name") or ""),
            completion_tokens=len(request.language),
            total_tokens=None,
        )

    def chat(self, request: ChatRequest) -> str:
        """A deterministic stand-in ground: cites only the given records.

        With no records it answers "not found" the way the system prompt
        requires; with records it summarises them. Tests can therefore assert
        grounding without a network.
        """
        message = request.user_message.strip().lower()
        if message in {"hi", "hello", "hey", "namaste", "vanakkam"}:
            return (
                "Hello! I am the SchemePing assistant. I can help you "
                "understand government schemes, documents and next steps. "
                "What would you like to know?"
            )
        if "No scheme records" in request.records:
            return (
                "I could not find any scheme that matches your question in "
                "the verified records. Please visit the nearest office "
                "listed in SchemePing or the official source."
            )
        records = _records_from(request.records)
        if records:
            names = ", ".join(str(record.get("name")) for record in records[:3])
            first = records[0]
            benefit = first.get("benefit_summary") or ""
            return (
                f"From the verified records: {names}. {first.get('name')}: "
                f"{benefit} Check the scheme page in SchemePing for documents "
                "and steps."
            )
        return (
            "I do not have verified details for that in my records. Please "
            "check the scheme page in SchemePing or the official source."
        )


def _records_from(records_block: str) -> list[dict[str, Any]]:
    """Read the JSON array after ``SCHEME RECORDS:`` from the prompt block."""
    marker = "SCHEME RECORDS:"
    if marker not in records_block:
        return []
    raw = records_block.split(marker, 1)[1].lstrip()
    try:
        payload, _ = json.JSONDecoder().raw_decode(raw)
    except ValueError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]
