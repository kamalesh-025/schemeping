"""Eligibility service: recompute, cards, and summary.

The service is the only bridge between the database and the pure engine:

1. Map ORM rows to plain-data profiles (``app.eligibility.context``).
2. Build contexts for the user, every family member, and the household.
3. Evaluate every published scheme with the deterministic engine.
4. Upsert one ``eligibility_results`` row per (person, scheme), always with
   the full reason list so every result is auditable.

Recompute runs when the profile or a family member changes, when a scheme is
published or edited, and via the manual ``POST /eligibility/recompute``
endpoint. The Phase 5 daily Celery job will call ``recompute_user`` too, which
is why it lives in the service layer rather than in a router.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.eligibility import engine
from app.eligibility.context import (
    PersonProfile,
    build_household_context,
    build_person_context,
)
from app.eligibility.explain import reason_line
from app.eligibility.priority import priority_level
from app.models.eligibility import EligibilityResult
from app.models.enums import EligibilityStatus, SchemeScope, SchemeStatus
from app.models.family import FamilyMember
from app.models.scheme import Scheme
from app.models.user import User

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"

_PRIORITY_RANK = {"high": 0, "medium": 1, "normal": 2}
_MAX_MISSING_FIELDS = 20


def _enum_value(value: object) -> str:
    """String value of a VARCHAR-backed enum, whether enum or plain str."""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


# ------------------------------------------------------------------ profiles


def _user_profile(user: User) -> PersonProfile:
    return PersonProfile(
        name=user.name,
        dob=user.dob,
        gender=_enum_value(user.gender) if user.gender else None,
        annual_income=user.annual_income,
        occupation=user.occupation,
        education=_enum_value(user.education) if user.education else None,
        marital_status=_enum_value(user.marital_status) if user.marital_status else None,
        state=user.state,
        district=user.district,
        pincode=user.pincode,
        is_disabled=user.is_disabled,
    )


def _member_profile(member: FamilyMember, head: PersonProfile) -> PersonProfile:
    """A family member lives with the user, so they inherit the address."""
    return PersonProfile(
        name=member.name,
        dob=member.dob,
        gender=_enum_value(member.gender) if member.gender else None,
        annual_income=member.annual_income,
        occupation=member.occupation,
        education_status=_enum_value(member.education_status)
        if member.education_status
        else None,
        relationship=_enum_value(member.relationship),
        state=head.state,
        district=head.district,
        pincode=head.pincode,
        is_student=member.is_student,
        is_disabled=member.is_disabled,
        is_widow=member.is_widow,
    )


# ------------------------------------------------------------------ recompute


@dataclass(frozen=True)
class RecomputeReport:
    people: int
    schemes: int
    created: int
    updated: int
    unchanged: int


def _sync_senior_flags(user: User) -> None:
    """Persist the derived ``is_senior`` flag (single derivation source)."""
    from app.services.profile import derive_flags

    for member in user.family_members:
        member.is_senior = derive_flags(member.dob).is_senior


def _upsert_result(
    db: Session,
    *,
    user: User,
    member_id: int | None,
    scheme: Scheme,
    outcome: engine.EligibilityOutcome,
) -> str:
    """Create or refresh one result row.

    The lookup mirrors the unique constraint ``uq_eligibility_results_
    person_scheme`` so repeated recomputes can never duplicate a row. In
    MySQL NULLs bypass unique constraints entirely; the explicit ``.is_(None)``
    filter is what keeps user-level rows unique.
    """
    member_filter = (
        EligibilityResult.family_member_id.is_(None)
        if member_id is None
        else EligibilityResult.family_member_id == member_id
    )
    row = db.scalar(
        select(EligibilityResult).where(
            EligibilityResult.user_id == user.id,
            EligibilityResult.scheme_id == scheme.id,
            member_filter,
        )
    )

    status = EligibilityStatus(outcome.status)
    reasons = [reason.as_dict() for reason in outcome.reasons]
    missing_fields = list(outcome.missing_fields)[:_MAX_MISSING_FIELDS]

    if row is None:
        db.add(
            EligibilityResult(
                user_id=user.id,
                family_member_id=member_id,
                scheme_id=scheme.id,
                status=status,
                reasons=reasons,
                missing_fields=missing_fields,
                computed_at=utcnow(),
            )
        )
        return CREATED

    if (
        row.status == status
        and row.reasons == reasons
        and row.missing_fields == missing_fields
    ):
        return UNCHANGED

    row.status = status
    row.reasons = reasons
    row.missing_fields = missing_fields
    row.computed_at = utcnow()
    return UPDATED


def recompute_user(db: Session, user: User) -> RecomputeReport:
    """Recompute eligibility for the user and every family member.

    Idempotent: re-running over an unchanged database reports everything as
    ``unchanged`` and never duplicates rows.
    """
    _sync_senior_flags(user)

    schemes = list(
        db.scalars(
            select(Scheme)
            .where(Scheme.status == SchemeStatus.PUBLISHED)
            .order_by(Scheme.id)
        ).all()
    )
    members = list(
        db.scalars(
            select(FamilyMember)
            .where(FamilyMember.user_id == user.id)
            .order_by(FamilyMember.id)
        ).all()
    )

    head = _user_profile(user)
    me_context = build_person_context(head)
    member_contexts = [
        (member.id, build_person_context(_member_profile(member, head)))
        for member in members
    ]
    household_context = build_household_context(
        head, [_member_profile(member, head) for member in members]
    )

    created = 0
    updated = 0
    unchanged = 0

    for scheme in schemes:
        rules = scheme.eligibility_rules

        candidates: list[tuple[int | None, engine.EligibilityOutcome]]
        if scheme.scope == SchemeScope.INDIVIDUAL:
            candidates = [(None, engine.evaluate(rules, me_context))]
            candidates += [
                (member_id, engine.evaluate(rules, context))
                for member_id, context in member_contexts
            ]
        else:
            candidates = [(None, engine.evaluate(rules, household_context))]

        for member_id, outcome in candidates:
            result = _upsert_result(
                db, user=user, member_id=member_id, scheme=scheme, outcome=outcome
            )
            if result == CREATED:
                created += 1
            elif result == UPDATED:
                updated += 1
            else:
                unchanged += 1

    db.commit()

    return RecomputeReport(
        people=1 + len(member_contexts),
        schemes=len(schemes),
        created=created,
        updated=updated,
        unchanged=unchanged,
    )


# ------------------------------------------------------------------ cards


def _days_remaining(deadline: date | None) -> int | None:
    if deadline is None:
        return None
    return (deadline - utcnow().date()).days


@dataclass(frozen=True)
class EligibilityCard:
    """One scheme card for the dashboard."""

    scheme_id: int
    slug: str
    name: str
    department: str
    level: str
    state: str | None
    category: str
    scope: str
    benefit_summary: str
    benefit_amount: str | None
    benefit_type: str
    status: str
    deadline: date | None
    days_remaining: int | None
    priority: str
    reason_line: str
    missing_fields: list[str]
    last_verified_on: date


def _sort_key(card: EligibilityCard) -> tuple[int, int, int]:
    if (
        card.deadline is not None
        and card.days_remaining is not None
        and card.days_remaining >= 0
    ):
        deadline_rank: int = card.days_remaining
    else:
        deadline_rank = 10**6
    return (_PRIORITY_RANK[card.priority], deadline_rank, card.scheme_id)


def list_cards(
    db: Session,
    user: User,
    *,
    person: str | int = "me",
    category: str | None = None,
    scope: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[EligibilityCard]]:
    """Return ``(total, cards)`` for the requested person after filters.

    ``person`` is ``"me"`` or a family member id (the router has already
    checked ownership). ``member_id IS NULL`` rows cover the user themself,
    household schemes, and event schemes — exactly what the dashboard shows
    for ``me``.

    Sorting: high priority first, then soonest still-open deadline, then
    scheme id, so the output is deterministic.
    """
    member_filter = (
        EligibilityResult.family_member_id.is_(None)
        if str(person) == "me"
        else EligibilityResult.family_member_id == int(person)
    )

    conditions: list[ColumnElement[bool]] = [
        EligibilityResult.user_id == user.id,
        member_filter,
        Scheme.status == SchemeStatus.PUBLISHED,
    ]
    if category:
        conditions.append(Scheme.category == category)
    if scope:
        conditions.append(Scheme.scope == SchemeScope(scope))
    if status_filter:
        conditions.append(EligibilityResult.status == EligibilityStatus(status_filter))

    selection = (
        select(EligibilityResult, Scheme)
        .join(Scheme, EligibilityResult.scheme_id == Scheme.id)
        .where(*conditions)
    )

    total = int(
        db.scalar(select(func.count()).select_from(selection.subquery())) or 0
    )
    rows = db.execute(selection).all()

    cards: list[EligibilityCard] = []
    for result, scheme in rows:
        status = _enum_value(result.status)
        days = _days_remaining(scheme.deadline)
        scheme_scope = _enum_value(scheme.scope)
        cards.append(
            EligibilityCard(
                scheme_id=scheme.id,
                slug=scheme.slug,
                name=scheme.name,
                department=scheme.department,
                level=_enum_value(scheme.level),
                state=scheme.state,
                category=scheme.category,
                scope=scheme_scope,
                benefit_summary=scheme.benefit_summary,
                benefit_amount=scheme.benefit_amount,
                benefit_type=_enum_value(scheme.benefit_type),
                status=status,
                deadline=scheme.deadline,
                days_remaining=days,
                priority=priority_level(
                    days_remaining=days, benefit_amount=scheme.benefit_amount
                ),
                reason_line=reason_line(status, result.reasons, result.missing_fields),
                missing_fields=list(result.missing_fields or []),
                last_verified_on=scheme.last_verified_on,
            )
        )

    cards.sort(key=_sort_key)
    return total, cards[offset : offset + limit]


def get_summary(db: Session, user: User) -> dict[str, object]:
    """Per-person and per-category counts over published schemes.

    Response shape::

        {"people": [{"kind": "me"|"family", "id": int|None, "name": str,
                     "counts": {eligible, needs_info, not_eligible, total},
                     "by_category": {category: {same counts}}}, ...]}

    Every person in the household is listed, even when they have no counts.
    """
    rows = db.execute(
        select(EligibilityResult, Scheme.category)
        .join(Scheme, EligibilityResult.scheme_id == Scheme.id)
        .where(
            EligibilityResult.user_id == user.id,
            Scheme.status == SchemeStatus.PUBLISHED,
        )
    ).all()

    def _empty_bucket() -> dict[str, object]:
        return {"counts": {}, "by_category": {}}

    people: dict[int | None, dict[str, Any]] = {None: _empty_bucket()}
    for result, category in rows:
        key = result.family_member_id
        person = people.setdefault(key, _empty_bucket())
        status_key = _enum_value(result.status)
        counts = person["counts"]
        counts[status_key] = counts.get(status_key, 0) + 1

        by_category = person["by_category"].setdefault(str(category), {})
        by_category[status_key] = by_category.get(status_key, 0) + 1

    ordered_people: list[dict[str, object]] = []
    me = people.get(None, _empty_bucket())
    ordered_people.append(
        {
            "kind": "me",
            "id": None,
            "name": user.name,
            "counts": _complete_counts(me["counts"]),
            "by_category": {
                category: _complete_counts(counts)
                for category, counts in me["by_category"].items()
            },
        }
    )
    for member in db.scalars(
        select(FamilyMember).where(FamilyMember.user_id == user.id).order_by(FamilyMember.id)
    ).all():
        bucket = people.get(member.id, _empty_bucket())
        ordered_people.append(
            {
                "kind": "family",
                "id": member.id,
                "name": member.name,
                "counts": _complete_counts(bucket["counts"]),
                "by_category": {
                    category: _complete_counts(counts)
                    for category, counts in bucket["by_category"].items()
                },
            }
        )

    return {"people": ordered_people}


def _complete_counts(raw: dict[str, int]) -> dict[str, int]:
    counts = dict.fromkeys(("eligible", "needs_info", "not_eligible"), 0)
    counts.update(raw)
    counts["total"] = sum(counts.values())
    return counts
