"""Eligibility dashboard endpoints.

Every route is scoped to the logged-in user; ``person`` must be ``me`` or one
of that user's family member ids. Reading the cards does not recompute: the
engine runs on profile/family changes, on scheme publish/import, and on the
explicit ``POST /eligibility/recompute``, so the endpoint stays a cheap read.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.family import FamilyMember
from app.schemas.eligibility import (
    CardsOut,
    EligibilityCardOut,
    EligibilityStatusLiteral,
    RecomputeOut,
    ScopeLiteral,
    SummaryOut,
)
from app.services.eligibility import list_cards, recompute_user

router = APIRouter(prefix="/eligibility", tags=["eligibility"])
logger = get_logger(__name__)

_PERSON_404 = "Person not found."


def _resolve_person(db: DbSession, user: CurrentUser, person: str) -> str | int:
    """Validate the ``person`` query parameter and normalise it for the service."""
    if person == "me":
        return "me"
    try:
        member_id = int(person)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=_PERSON_404) from exc

    member = db.scalar(
        select(FamilyMember.id).where(
            FamilyMember.id == member_id, FamilyMember.user_id == user.id
        )
    )
    if member is None:
        # 404 rather than 403 so ids of other users' members stay hidden.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=_PERSON_404)
    return member_id


@router.get("", response_model=CardsOut, summary="Scheme cards for one person")
def card_list(
    user: CurrentUser,
    db: DbSession,
    person: Annotated[str, Query(description="'me' or a family member id")] = "me",
    category: Annotated[str | None, Query(max_length=64)] = None,
    scope: ScopeLiteral | None = None,
    status_filter: Annotated[
        EligibilityStatusLiteral | None, Query(alias="status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CardsOut:
    resolved = _resolve_person(db, user, person)
    total, cards = list_cards(
        db,
        user,
        person=resolved,
        category=category,
        scope=scope,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return CardsOut(
        total=total, cards=[EligibilityCardOut.model_validate(card) for card in cards]
    )


@router.get(
    "/summary", response_model=SummaryOut, summary="Per-person and per-category counts"
)
def summary(user: CurrentUser, db: DbSession) -> SummaryOut:
    from app.services.eligibility import get_summary

    return SummaryOut.model_validate(get_summary(db, user))


@router.post(
    "/recompute", response_model=RecomputeOut, summary="Recompute my eligibility"
)
def run_recompute(user: CurrentUser, db: DbSession) -> RecomputeOut:
    report = recompute_user(db, user)
    logger.info(
        "eligibility_recomputed",
        extra={
            "user_id": user.id,
            "results_created": report.created,
            "results_updated": report.updated,
        },
    )
    return RecomputeOut(
        people=report.people,
        schemes=report.schemes,
        created=report.created,
        updated=report.updated,
        unchanged=report.unchanged,
    )
