"""Privacy endpoints: consent record and full data export (Phase 6 Part D).

DPDP Act 2023 asks for transparency and access: a citizen must be able to
see what they consented to and download everything we hold about them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.time import ensure_utc
from app.models.chat import ChatMessage
from app.models.eligibility import EligibilityResult
from app.models.family import FamilyMember
from app.models.notification import Notification
from app.models.scheme import Scheme

router = APIRouter(tags=["privacy"])


def _iso_date(value: object) -> Any:
    """DOB is stored encrypted; it may be a date, a string, or absent."""
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class ConsentOut(BaseModel):
    data_processing: bool
    whatsapp: bool
    policy_version: str | None
    consented_at: datetime | None
    whatsapp_opted_out_at: datetime | None
    notification_preferences: dict[str, bool]


class DataExport(BaseModel):
    exported_at: datetime
    account: dict[str, Any]
    family_members: list[dict[str, Any]]
    eligibility_results: list[dict[str, Any]]
    notifications: list[dict[str, Any]]
    chat_messages: list[dict[str, Any]]


def _text(value: object) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(getattr(value, "value", value))


@router.get("/me/consents", response_model=ConsentOut)
def read_consents(user: CurrentUser) -> ConsentOut:
    from app.services.notification_prefs import merge_notification_prefs

    return ConsentOut(
        data_processing=user.consent_data_processing,
        whatsapp=user.consent_whatsapp,
        policy_version=user.consent_version,
        consented_at=ensure_utc(user.consented_at),
        whatsapp_opted_out_at=ensure_utc(user.whatsapp_opted_out_at),
        notification_preferences=merge_notification_prefs(user.notification_prefs),
    )


@router.get("/me/export")
def export_my_data(user: CurrentUser, db: DbSession) -> Response:
    """Everything we hold about this account, as a downloadable JSON file."""
    from app.core.time import utcnow

    members = db.scalars(
        select(FamilyMember).where(FamilyMember.user_id == user.id)
    ).all()
    results = db.scalars(
        select(EligibilityResult).where(EligibilityResult.user_id == user.id)
    ).all()
    notifications = db.scalars(
        select(Notification).where(Notification.user_id == user.id)
    ).all()
    chats = db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == user.id)
    ).all()

    scheme_names = {
        scheme.id: scheme.name
        for scheme in db.scalars(select(Scheme)).all()
    }

    payload = DataExport(
        exported_at=utcnow(),
        account={
            "id": user.id,
            "name": user.name,
            "mobile": user.mobile,
            "dob": _iso_date(user.dob),
            "gender": user.gender,
            "annual_income": user.annual_income,
            "is_disabled": user.is_disabled,
            "occupation": user.occupation,
            "education": _text(user.education),
            "marital_status": _text(user.marital_status),
            "state": user.state,
            "district": user.district,
            "locality": user.locality,
            "pincode": user.pincode,
            "language": _text(user.language),
            "consent_data_processing": user.consent_data_processing,
            "consent_whatsapp": user.consent_whatsapp,
            "consent_version": user.consent_version,
            "consented_at": ensure_utc(user.consented_at),
            "created_at": ensure_utc(user.created_at),
        },
        family_members=[
            {
                "id": member.id,
                "name": member.name,
                "relationship": _text(member.relationship),
                "dob": _iso_date(member.dob),
                "gender": member.gender,
                "annual_income": member.annual_income,
                "is_disabled": member.is_disabled,
                "is_student": member.is_student,
                "is_widow": member.is_widow,
                "occupation": member.occupation,
                "education_status": member.education_status,
            }
            for member in members
        ],
        eligibility_results=[
            {
                "scheme_id": result.scheme_id,
                "scheme_name": scheme_names.get(result.scheme_id),
                "family_member_id": result.family_member_id,
                "status": _text(result.status),
                "reasons": list(result.reasons or []),
                "missing_fields": list(result.missing_fields or []),
                "computed_at": ensure_utc(result.computed_at),
            }
            for result in results
        ],
        notifications=[
            {
                "id": notification.id,
                "type": _text(notification.type),
                "template_name": notification.template_name,
                "status": _text(notification.status),
                "payload": dict(notification.payload or {}),
                "created_at": ensure_utc(notification.created_at),
                "sent_at": ensure_utc(notification.sent_at),
            }
            for notification in notifications
        ],
        chat_messages=[
            {
                "id": message.id,
                "role": _text(message.role),
                "content": message.content,
                "language": _text(message.language),
                "created_at": ensure_utc(message.created_at),
            }
            for message in chats
        ],
    )

    import json

    body = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="schemeping-my-data.json"'
        },
    )
