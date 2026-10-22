"""Family member CRUD. Every query is scoped to the current user."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.models.family import FamilyMember
from app.schemas.family import (
    FamilyMemberCreateIn,
    FamilyMemberOut,
    FamilyMemberUpdateIn,
)
from app.services.eligibility import recompute_user
from app.services.profile import derive_flags

router = APIRouter(prefix="/family", tags=["family"])
logger = get_logger(__name__)

MAX_FAMILY_MEMBERS = 20


def _payload(member: FamilyMember) -> FamilyMemberOut:
    flags = derive_flags(member.dob)
    return FamilyMemberOut(
        id=member.id,
        name=member.name,
        relationship=member.relationship,
        dob=member.dob,
        gender=member.gender,
        occupation=member.occupation,
        education_status=member.education_status,
        annual_income=member.annual_income,
        is_disabled=member.is_disabled,
        is_student=member.is_student,
        is_widow=member.is_widow,
        age=flags.age,
        is_senior=flags.is_senior,
        is_minor=flags.is_minor,
        created_at=member.created_at,
        updated_at=member.updated_at,
    )


def _owned_member(db: DbSession, user_id: int, member_id: int) -> FamilyMember:
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.id == member_id, FamilyMember.user_id == user_id
        )
    )
    if member is None:
        # 404 rather than 403 so the API does not reveal that another user's
        # family member id exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Family member not found."
        )
    return member


def _sync_derived_flags(member: FamilyMember) -> None:
    """Persist ``is_senior`` so Phase 3 SQL filters can use the column."""
    member.is_senior = derive_flags(member.dob).is_senior


@router.get("", response_model=list[FamilyMemberOut], summary="List my family members")
def list_family(user: CurrentUser, db: DbSession) -> list[FamilyMemberOut]:
    members = db.scalars(
        select(FamilyMember)
        .where(FamilyMember.user_id == user.id)
        .order_by(FamilyMember.id)
    ).all()
    return [_payload(member) for member in members]


@router.post(
    "",
    response_model=FamilyMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a family member",
)
def create_family_member(
    payload: FamilyMemberCreateIn, user: CurrentUser, db: DbSession
) -> FamilyMemberOut:
    existing_count = len(
        db.scalars(select(FamilyMember.id).where(FamilyMember.user_id == user.id)).all()
    )
    if existing_count >= MAX_FAMILY_MEMBERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You can add up to {MAX_FAMILY_MEMBERS} family members.",
        )

    member = FamilyMember(
        user_id=user.id,
        name=payload.name,
        relationship=payload.relationship,
        dob=payload.dob,
        gender=payload.gender.value if payload.gender else None,
        occupation=payload.occupation,
        education_status=payload.education_status,
        annual_income=payload.annual_income,
        is_disabled=payload.is_disabled,
        is_student=payload.is_student,
        is_widow=payload.is_widow,
    )
    _sync_derived_flags(member)
    db.add(member)
    db.commit()
    db.refresh(member)
    recompute_user(db, user)
    logger.info(
        "family_member_created", extra={"user_id": user.id, "member_id": member.id}
    )
    return _payload(member)


@router.get("/{member_id}", response_model=FamilyMemberOut, summary="Read one family member")
def read_family_member(member_id: int, user: CurrentUser, db: DbSession) -> FamilyMemberOut:
    return _payload(_owned_member(db, user.id, member_id))


@router.patch(
    "/{member_id}", response_model=FamilyMemberOut, summary="Update a family member"
)
def update_family_member(
    member_id: int, payload: FamilyMemberUpdateIn, user: CurrentUser, db: DbSession
) -> FamilyMemberOut:
    member = _owned_member(db, user.id, member_id)

    changes = payload.model_dump(exclude_unset=True)
    for field_name, value in changes.items():
        if field_name == "gender" and value is not None:
            member.gender = value.value
        else:
            setattr(member, field_name, value)

    if "dob" in changes:
        _sync_derived_flags(member)

    db.add(member)
    db.commit()
    db.refresh(member)
    recompute_user(db, user)
    return _payload(member)


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a family member",
)
def delete_family_member(member_id: int, user: CurrentUser, db: DbSession) -> None:
    member = _owned_member(db, user.id, member_id)
    db.delete(member)
    db.commit()
    recompute_user(db, user)
    logger.info("family_member_deleted", extra={"user_id": user.id, "member_id": member_id})
