"""Scheme detail assembly.

Combines three verified sources into one response:

1. The admin-authored scheme record (documents, steps, deadline, source).
2. The cached simplified translation for the requested language, generated
   on first use through the LLM provider interface and stored in
   ``scheme_translations`` (see ``services.translations``).
3. The person's eligibility outcome. The stored ``eligibility_results`` row
   from the last recompute is used when present; otherwise the pure engine
   is evaluated directly for that person with the same context builders as
   ``recompute_user``, so the endpoint never invents or guesses.

The "why you qualify" sentences are produced by the deterministic template
in ``app.eligibility.explain`` — never by the LLM.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.eligibility import engine
from app.eligibility.context import (
    PersonProfile,
    build_household_context,
    build_person_context,
)
from app.eligibility.explain import explain_facts
from app.models.eligibility import EligibilityResult
from app.models.enums import SchemeScope, SchemeStatus
from app.models.family import FamilyMember
from app.models.scheme import Scheme, SchemeTranslation
from app.models.user import User
from app.services.eligibility import _days_remaining, _member_profile, _user_profile


class SchemeNotFoundError(LookupError):
    """The scheme is unknown to the user (draft, archived, or missing)."""


class PersonNotFoundError(LookupError):
    """The requested person is not me or a member of this user."""


def load_published_scheme(db: Session, scheme_id: int) -> Scheme:
    scheme = db.get(Scheme, scheme_id)
    if scheme is None or scheme.status != SchemeStatus.PUBLISHED:
        # 404 (not 403) so drafts never leak their existence to users.
        raise SchemeNotFoundError(f"Scheme {scheme_id} not found")
    return scheme


def _resolve_person(db: Session, user: User, person: str | int) -> FamilyMember | None:
    if person == "me" or int(person) == 0:
        return None
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.id == int(person), FamilyMember.user_id == user.id
        )
    )
    if member is None:
        raise PersonNotFoundError(f"Person {person} not found")
    return member


def _stored_result(
    db: Session, user_id: int, scheme_id: int, member_id: int | None
) -> EligibilityResult | None:
    member_filter = (
        EligibilityResult.family_member_id.is_(None)
        if member_id is None
        else EligibilityResult.family_member_id == member_id
    )
    return db.scalar(
        select(EligibilityResult).where(
            EligibilityResult.user_id == user_id,
            EligibilityResult.scheme_id == scheme_id,
            member_filter,
        )
    )


def _head_and_members(user: User) -> tuple[PersonProfile, list[PersonProfile]]:
    head = _user_profile(user)
    members = [_member_profile(member, head) for member in user.family_members]
    return head, members


def _evaluate_fresh(
    db: Session, user: User, scheme: Scheme, member: FamilyMember | None
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """Deterministic fallback when no stored result exists yet.

    Same builders as ``recompute_user``: identical outcomes, stored or not.
    """
    head, member_profiles = _head_and_members(user)
    rules = scheme.eligibility_rules

    if scheme.scope == SchemeScope.FAMILY:
        context = build_household_context(head, member_profiles)
        outcome = engine.evaluate(rules, context)
    else:
        if member is None:
            context = build_person_context(head)
        else:
            context = build_person_context(_member_profile(member, head))
        outcome = engine.evaluate(rules, context)

    return (
        outcome.status,
        [reason.as_dict() for reason in outcome.reasons],
        list(outcome.missing_fields),
    )


def _type_value(value: object) -> str:
    return str(getattr(value, "value", value))


def build_detail(
    db: Session,
    user: User,
    scheme: Scheme,
    *,
    language: str,
    person: str | int = "me",
    translation: SchemeTranslation | None = None,
    translation_cached: bool = False,
    translation_fallback: bool = False,
) -> dict[str, Any]:
    """One complete, verified detail payload."""
    member = _resolve_person(db, user, person)
    member_id = member.id if member is not None else None

    result = _stored_result(db, user.id, scheme.id, member_id)
    if result is not None:
        status = _type_value(result.status)
        reasons = list(result.reasons or [])
        missing_fields = list(result.missing_fields or [])
    else:
        status, reasons, missing_fields = _evaluate_fresh(db, user, scheme, member)

    documents = [
        {"name": str(doc.get("name", "")).strip(), "notes": doc.get("notes")}
        for doc in (scheme.required_documents or [])
        if doc.get("name")
    ]
    steps = [
        {"title": str(step.get("title", "")).strip(), "detail": step.get("description")}
        for step in (scheme.application_steps or [])
        if step.get("title") or step.get("description")
    ]

    payload: dict[str, Any] = {
        "id": scheme.id,
        "slug": scheme.slug,
        "name": scheme.name,
        "department": scheme.department,
        "level": _type_value(scheme.level),
        "state": scheme.state,
        "category": scheme.category,
        "scope": _type_value(scheme.scope),
        "benefit_summary": scheme.benefit_summary,
        "benefit_amount": scheme.benefit_amount,
        "benefit_type": _type_value(scheme.benefit_type),
        "deadline": scheme.deadline.isoformat() if scheme.deadline else None,
        "days_remaining": _days_remaining(scheme.deadline),
        "apply_url": scheme.apply_url,
        "source_url": scheme.source_url,
        "last_verified_on": (
            scheme.last_verified_on.isoformat() if scheme.last_verified_on else None
        ),
        "required_documents": documents,
        "application_steps": steps,
        "eligibility_status": status,
        "why_qualify": explain_facts(status, reasons, missing_fields),
        "missing_fields": missing_fields,
        "person": "me" if member is None else member.id,
        "language": language,
    }

    if translation is not None:
        payload["translation"] = {
            "simple_title": translation.simple_title,
            "simple_description": translation.simple_description,
            "simple_benefits": list(translation.simple_benefits or []),
            "simple_steps": list(translation.simple_steps or []),
            "cached": translation_cached,
            "fallback": translation_fallback,
        }
    return payload
