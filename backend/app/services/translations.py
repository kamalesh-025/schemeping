"""Cached LLM simplification and translation.

Rules implemented here:

- Content hash: SHA-256 over the canonical serialisation of every scheme
  field that affects the explanation. A translation row is a cache hit only
  when ``(scheme_id, language, source_hash)`` all match, so editing a scheme
  invalidates its translations without any extra bookkeeping.
- Lazy generation: the first ``GET /schemes/{id}?lang=`` call generates and
  stores the row; every later call for the same content is a pure read and
  never reaches the provider.
- Fallback: when the provider fails (quota, outage, invalid JSON), the
  response is built from the admin-written English text and flagged
  ``fallback=True``. The English text is what the admin verified, so it is
  never wrong even when the model is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import Language
from app.models.scheme import Scheme, SchemeTranslation
from app.services.llm import LLMError, LLMProvider, SimplificationRequest
from app.services.llm import get_llm_provider as _default_provider_factory

logger = logging.getLogger(__name__)

_HASHED_FIELDS = (
    "name",
    "department",
    "level",
    "state",
    "category",
    "scope",
    "benefit_summary",
    "benefit_amount",
    "benefit_type",
    "eligibility_rules",
    "required_documents",
    "application_steps",
    "apply_url",
    "deadline",
)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def content_hash(scheme: Scheme) -> str:
    """Stable hash of the scheme fields that produce the explanation."""
    payload = {
        field: _enum_value(getattr(scheme, field))
        if not isinstance(getattr(scheme, field), (dict, list))
        else getattr(scheme, field)
        for field in _HASHED_FIELDS
    }
    serialised = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def scheme_record(scheme: Scheme) -> dict[str, Any]:
    """Public scheme text for the model. No user data ever enters here."""
    return {
        "slug": scheme.slug,
        "name": scheme.name,
        "department": scheme.department,
        "level": _enum_value(scheme.level),
        "state": scheme.state,
        "category": scheme.category,
        "benefit_summary": scheme.benefit_summary,
        "benefit_amount": scheme.benefit_amount,
        "benefit_type": _enum_value(scheme.benefit_type),
        "eligibility_summary": None,
        "required_documents": [
            {"name": doc.get("name"), "notes": doc.get("notes")}
            for doc in (scheme.required_documents or [])
        ],
        "application_steps": [
            {"title": step.get("title"), "description": step.get("description")}
            for step in (scheme.application_steps or [])
        ],
        "apply_url": scheme.apply_url,
        "deadline": scheme.deadline.isoformat() if scheme.deadline else None,
    }


def _fallback_content(scheme: Scheme) -> tuple[str, str, list[str], list[str]]:
    """Admin-authored English text used when the provider fails."""
    benefits = [scheme.benefit_summary]
    if scheme.benefit_amount:
        benefits.insert(0, scheme.benefit_amount)
    steps = [
        str(step.get("title") or step.get("description") or "").strip()
        for step in (scheme.application_steps or [])
        if step.get("title") or step.get("description")
    ]
    return scheme.name, scheme.benefit_summary, benefits, steps


@dataclass(frozen=True)
class TranslationResult:
    translation: SchemeTranslation
    cached: bool
    fallback: bool


def get_or_generate_translation(
    db: Session,
    scheme: Scheme,
    language: str,
    *,
    provider: LLMProvider | None = None,
    provider_factory: Any = _default_provider_factory,
) -> TranslationResult:
    """Return the cached translation row, generating it only when needed."""
    lang = Language(language)
    current_hash = content_hash(scheme)

    row = db.scalar(
        select(SchemeTranslation).where(
            SchemeTranslation.scheme_id == scheme.id,
            SchemeTranslation.language == lang,
        )
    )
    if row is not None and row.source_hash == current_hash:
        return TranslationResult(translation=row, cached=True, fallback=False)

    provider = provider if provider is not None else provider_factory()
    record = scheme_record(scheme)

    try:
        content = provider.simplify_and_translate(
            SimplificationRequest(scheme=record, language=lang.value)
        )
        simple_title = content.simple_title
        simple_description = content.simple_description
        simple_benefits = list(content.simple_benefits)
        simple_steps = list(content.simple_steps)
        generated_by = provider.name
        model_name = content.model_name
        fallback = False

        logger.info(
            "translation_generated",
            extra={
                "scheme_id": scheme.id,
                "language": lang.value,
                "provider": generated_by,
                "prompt_tokens": content.prompt_tokens,
                "completion_tokens": content.completion_tokens,
                "total_tokens": content.total_tokens,
            },
        )
    except LLMError as exc:
        logger.warning(
            "translation_fallback",
            extra={
                "scheme_id": scheme.id,
                "language": lang.value,
                "provider": provider.name,
                "error": str(exc)[:200],
            },
        )
        simple_title, simple_description, simple_benefits, simple_steps = (
            _fallback_content(scheme)
        )
        generated_by = "fallback"
        model_name = None
        fallback = True

    if row is None:
        row = SchemeTranslation(scheme_id=scheme.id, language=lang)
        db.add(row)
    row.simple_title = simple_title
    row.simple_description = simple_description
    row.simple_benefits = simple_benefits
    row.simple_steps = simple_steps
    row.generated_by = generated_by
    row.model_name = model_name
    row.source_hash = current_hash
    db.commit()
    return TranslationResult(translation=row, cached=False, fallback=fallback)
