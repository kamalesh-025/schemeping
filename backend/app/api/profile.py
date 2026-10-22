"""Profile, consent, and account-deletion routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import delete

from app.api.deps import CurrentUser, DbSession, clear_session_cookies
from app.core.logging import get_logger
from app.core.time import utcnow
from app.models.user import User
from app.schemas.auth import ConsentOut, ConsentUpdateIn
from app.schemas.profile import (
    POLICY_VERSION,
    DeleteAccountIn,
    ProfileOut,
    ProfileUpdateIn,
)
from app.services.eligibility import recompute_user
from app.services.profile import derive_flags, is_profile_complete

router = APIRouter(tags=["profile"])
logger = get_logger(__name__)


def _profile_payload(user: User) -> ProfileOut:
    flags = derive_flags(user.dob)
    return ProfileOut(
        id=user.id,
        mobile=user.mobile,
        name=user.name,
        dob=user.dob,
        gender=user.gender,
        occupation=user.occupation,
        annual_income=user.annual_income,
        is_disabled=user.is_disabled,
        education=user.education,
        marital_status=user.marital_status,
        state=user.state,
        district=user.district,
        locality=user.locality,
        pincode=user.pincode,
        language=user.language,
        consent_data_processing=user.consent_data_processing,
        consent_whatsapp=user.consent_whatsapp,
        consent_version=user.consent_version,
        consented_at=user.consented_at,
        whatsapp_opted_out_at=user.whatsapp_opted_out_at,
        profile_complete=is_profile_complete(user),
        age=flags.age,
        is_senior=flags.is_senior,
        created_at=user.created_at,
    )


@router.get("/me", response_model=ProfileOut, summary="Read my profile")
def read_me(user: CurrentUser) -> ProfileOut:
    return _profile_payload(user)


@router.put("/me", response_model=ProfileOut, summary="Replace my profile")
def update_me(payload: ProfileUpdateIn, user: CurrentUser, db: DbSession) -> ProfileOut:
    user.name = payload.name
    user.dob = payload.dob
    user.gender = payload.gender.value
    user.occupation = payload.occupation
    user.annual_income = payload.annual_income
    user.is_disabled = payload.is_disabled
    user.education = payload.education
    user.marital_status = payload.marital_status
    user.state = payload.state
    user.district = payload.district
    user.locality = payload.locality
    user.pincode = payload.pincode
    user.language = payload.language

    # Data-processing consent is required to save a profile (DPDP Act 2023).
    if payload.data_processing_consent is not None:
        if payload.data_processing_consent and not user.consent_data_processing:
            user.consent_data_processing = True
            user.consented_at = utcnow()
            user.consent_version = POLICY_VERSION
        elif not payload.data_processing_consent:
            # Withdrawing processing consent is an account-level action.
            user.consent_data_processing = False

    if payload.whatsapp_opt_in is not None:
        _apply_whatsapp_choice(user, payload.whatsapp_opt_in)

    db.add(user)
    db.commit()
    db.refresh(user)
    # Phase 3: profile changes may flip eligibility; recompute right away.
    recompute_user(db, user)
    return _profile_payload(user)


@router.get("/me/consent", response_model=ConsentOut, summary="Read consent state")
def read_consent(user: CurrentUser) -> ConsentOut:
    return ConsentOut(
        data_processing=user.consent_data_processing,
        whatsapp_opt_in=user.consent_whatsapp,
        consented_at=user.consented_at,
        whatsapp_opted_out_at=user.whatsapp_opted_out_at,
        policy_version=user.consent_version,
    )


@router.patch(
    "/me/consent/whatsapp",
    response_model=ConsentOut,
    summary="Opt in or out of WhatsApp messages",
)
def update_whatsapp_consent(
    payload: ConsentUpdateIn, user: CurrentUser, db: DbSession
) -> ConsentOut:
    _apply_whatsapp_choice(user, payload.whatsapp_opt_in)
    db.add(user)
    db.commit()
    db.refresh(user)
    return read_consent(user)


def _apply_whatsapp_choice(user: User, opt_in: bool) -> None:
    if opt_in:
        user.consent_whatsapp = True
        user.whatsapp_opted_out_at = None
    else:
        user.consent_whatsapp = False
        user.whatsapp_opted_out_at = utcnow()


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete my account and all family data",
)
def delete_me(
    payload: DeleteAccountIn, user: CurrentUser, db: DbSession, response: Response
) -> Response:
    # Hard delete. Family members, notifications, eligibility results, chat
    # messages, and refresh tokens all cascade from users.id.
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    clear_session_cookies(response)
    logger.info("account_deleted", extra={"user_id": user.id})
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
