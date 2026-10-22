"""Scheme detail endpoint.

``GET /schemes/{scheme_id}?lang=&person=``

- Draft and archived schemes 404, exactly like unknown ids: unpublished data
  must never leak its existence (AGENTS.md 4).
- ``lang`` defaults to the user's preferred language; only the six app
  languages are accepted.
- ``person`` is ``"me"`` or a family member id owned by the caller; the
  eligibility outcome and "why you qualify" sentences are rendered by the
  deterministic engine template for that person — the LLM never shapes
  eligibility wording.
- The translation is generated lazily per language and cached in
  ``scheme_translations``; this call is the cache-and-generate step.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.schemas.scheme import LanguageLiteral, SchemeDetailOut
from app.services.llm import get_llm_provider
from app.services.schemes import (
    PersonNotFoundError,
    SchemeNotFoundError,
    build_detail,
    load_published_scheme,
)
from app.services.translations import get_or_generate_translation

router = APIRouter(prefix="/schemes", tags=["schemes"])
logger = get_logger(__name__)


@router.get("/{scheme_id}", response_model=SchemeDetailOut, summary="Scheme detail")
def scheme_detail(
    user: CurrentUser,
    db: DbSession,
    scheme_id: int,
    lang: LanguageLiteral | None = None,
    person: Annotated[str, Query(description="'me' or a family member id")] = "me",
) -> SchemeDetailOut:
    try:
        scheme = load_published_scheme(db, scheme_id)
    except SchemeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Scheme not found.") from exc

    language: str = lang or "en"
    try:
        resolved_person: str | int = "me" if person == "me" else int(person)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Person not found.") from exc

    try:
        result = get_or_generate_translation(db, scheme, language)
    except ValueError as exc:
        # Language out of the six supported codes.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown language.") from exc

    try:
        payload = build_detail(
            db,
            user,
            scheme,
            language=language,
            person=resolved_person,
            translation=result.translation,
            translation_cached=result.cached,
            translation_fallback=result.fallback,
        )
    except PersonNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person not found.") from exc

    logger.info(
        "scheme_detail_served",
        extra={
            "scheme_id": scheme.id,
            "language": language,
            "translation_cached": result.cached,
            "translation_fallback": result.fallback,
            "provider": get_llm_provider().name
            if not result.cached
            else result.translation.generated_by,
        },
    )
    return SchemeDetailOut.model_validate(payload)
