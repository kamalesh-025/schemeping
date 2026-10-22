"""User notifications: list, preferences, send-to-WhatsApp, provider webhook."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.time import ensure_utc, utcnow
from app.models.enums import NotificationStatus, NotificationType
from app.models.notification import Notification
from app.services import notifications as notifications_service

logger = get_logger(__name__)

router = APIRouter(tags=["notifications"])


# ------------------------------------------------------------------ models


class NotificationOut(BaseModel):
    id: int
    type: NotificationType
    template_name: str
    status: NotificationStatus
    payload: dict[str, Any]
    created_at: datetime
    sent_at: datetime | None
    delivered_at: datetime | None
    error: str | None


class NotificationsOut(BaseModel):
    total: int
    notifications: list[NotificationOut]


class NotificationPrefsIn(BaseModel):
    new_schemes: bool | None = None
    family_milestones: bool | None = None
    deadlines: bool | None = None
    festival: bool | None = None


class NotificationPrefsOut(BaseModel):
    new_schemes: bool
    family_milestones: bool
    deadlines: bool
    festival: bool


class SendWhatsappOut(BaseModel):
    status: Literal["queued", "skipped", "failed"]
    reason: str | None = None
    notification_id: int | None = None


# ------------------------------------------------------------------ list + prefs


@router.get("/notifications", response_model=NotificationsOut)
def list_notifications(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=100),
) -> NotificationsOut:
    rows: Sequence[Notification] = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
        .limit(limit)
    ).all()
    return NotificationsOut(
        total=len(rows),
        notifications=[
            NotificationOut(
                id=row.id,
                type=row.type,
                template_name=row.template_name,
                status=row.status,
                payload=dict(row.payload or {}),
                created_at=ensure_utc(row.created_at),
                sent_at=ensure_utc(row.sent_at),
                delivered_at=ensure_utc(row.delivered_at),
                error=row.error,
            )
            for row in rows
        ],
    )


@router.get("/me/notification-prefs", response_model=NotificationPrefsOut)
def read_notification_prefs(user: CurrentUser) -> NotificationPrefsOut:
    from app.services.notification_prefs import merge_notification_prefs

    return NotificationPrefsOut(**merge_notification_prefs(user.notification_prefs))


@router.patch("/me/notification-prefs", response_model=NotificationPrefsOut)
def update_notification_prefs(
    payload: NotificationPrefsIn, user: CurrentUser, db: DbSession
) -> NotificationPrefsOut:
    from app.services.notification_prefs import merge_notification_prefs

    current = merge_notification_prefs(user.notification_prefs)
    changed = {key: value for key, value in payload.model_dump().items() if value is not None}
    current.update(changed)
    user.notification_prefs = current
    db.commit()
    return NotificationPrefsOut(**current)


# ------------------------------------------------------------------ send to WhatsApp


@router.post(
    "/schemes/{scheme_id}/send-whatsapp",
    response_model=SendWhatsappOut,
    summary="Send this scheme's summary to my WhatsApp",
)
def send_scheme_to_whatsapp(
    scheme_id: int,
    user: CurrentUser,
    db: DbSession,
    person: str | None = Query(default=None),
    language: str | None = Query(default=None),
) -> SendWhatsappOut:
    """Queue the pre-approved ``scheme_summary`` template in the user's language.

    Opt-in is enforced here even though the queueing service re-checks: the
    button state is a user experience question, the queue is the guarantee.
    """
    blocking = notifications_service.can_send_on_request(user)
    if blocking is not None:
        return SendWhatsappOut(
            status="skipped",
            reason="not_opted_in" if blocking == "not_opted_in" else blocking,
        )

    if notifications_service.send_whatsapp_rate_limited(db, user.id):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You can send 10 scheme summaries per hour. Please try later.",
        )

    ok, params_or_error = notifications_service.build_scheme_summary_params(
        db,
        user,
        scheme_id,
        language=language or notifications_service.user_language(user),
        person=person or "me",
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(params_or_error))

    params: dict[str, str] = params_or_error  # type: ignore[assignment]
    person_value: str = person or "me"
    dedupe = notifications_service.summary_dedupe_key(
        scheme_id, person_value, utcnow()
    )
    outcome = notifications_service.queue_notification(
        db,
        user,
        notification_type=NotificationType.SCHEME_SUMMARY,
        template_name="scheme_summary",
        params=params,
        dedupe_key=dedupe,
        skip_prefs=True,
        on_request=True,
    )
    if outcome.queued and outcome.notification is not None:
        return SendWhatsappOut(
            status="queued",
            notification_id=outcome.notification.id,
        )
    return SendWhatsappOut(status="skipped", reason=outcome.skipped)


# ------------------------------------------------------------------ delivery webhook


@router.get("/notifications/webhook", include_in_schema=False)
def verify_meta_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Complete Meta's webhook subscription challenge."""
    settings = get_settings()
    if (
        settings.whatsapp_provider != "meta"
        or mode != "subscribe"
        or not verify_token
        or not hmac.compare_digest(verify_token, settings.meta_whatsapp_verify_token)
        or not challenge
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid challenge")
    return Response(content=challenge, media_type="text/plain")


_STATUS_MAP: dict[str, NotificationStatus] = {
    "sent": NotificationStatus.SENT,
    "delivered": NotificationStatus.DELIVERED,
    "read": NotificationStatus.DELIVERED,
    "failed": NotificationStatus.FAILED,
    "undeliverable": NotificationStatus.FAILED,
    "rejected": NotificationStatus.FAILED,
}


def _extract(body: dict[str, Any]) -> tuple[str | None, NotificationStatus | None]:
    """Read common MSG91 events and Meta's nested delivery-status payload."""
    for entry in body.get("entry", []) if isinstance(body.get("entry"), list) else []:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            statuses = value.get("statuses")
            if not isinstance(statuses, list):
                continue
            for item in statuses:
                if not isinstance(item, dict):
                    continue
                message_id = item.get("id")
                mapped = _STATUS_MAP.get(str(item.get("status", "")).lower())
                if message_id and mapped:
                    return str(message_id), mapped

    for probe in (body, body.get("payload") if isinstance(body.get("payload"), dict) else body):
        if not isinstance(probe, dict):
            continue
        message_id = probe.get("message_id") or probe.get("request_id") or probe.get("id")
        raw_status = probe.get("status") or probe.get("dlr_status") or probe.get("event")
        mapped = _STATUS_MAP.get(str(raw_status).lower()) if raw_status else None
        if message_id and mapped:
            return str(message_id), mapped
    return None, None


@router.post("/notifications/webhook")
async def delivery_webhook(
    request: Request,
    db: DbSession,
    x_webhook_secret: Annotated[str | None, Header(alias="X-Webhook-Secret")] = None,
    x_hub_signature_256: Annotated[
        str | None, Header(alias="X-Hub-Signature-256")
    ] = None,
    secret: str | None = Query(default=None),
) -> dict[str, str]:
    """Provider delivery callback: Meta HMAC signature or MSG91 shared secret.

    Meta signs the raw request body with the app secret; MSG91 uses a shared
    secret header or query parameter.
    """
    settings = get_settings()
    raw_body = await request.body()
    if settings.whatsapp_provider == "meta":
        expected = (
            "sha256="
            + hmac.new(
                settings.meta_whatsapp_app_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()
            if settings.meta_whatsapp_app_secret
            else ""
        )
        if (
            not expected
            or not x_hub_signature_256
            or not hmac.compare_digest(x_hub_signature_256, expected)
        ):
            logger.warning("webhook_rejected", extra={"reason": "bad_meta_signature"})
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid signature")
    else:
        supplied = x_webhook_secret or secret
        if not supplied or not hmac.compare_digest(
            supplied, settings.whatsapp_webhook_secret
        ):
            logger.warning("webhook_rejected", extra={"reason": "bad_secret"})
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret"
            )

    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Request body must be valid JSON",
        ) from exc
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook body must be a JSON object",
        )

    message_id, delivery_status = _extract(body)
    if not message_id or delivery_status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not read message_id and status from the payload",
        )

    row = db.scalar(
        select(Notification).where(Notification.provider_message_id == message_id)
    )
    if row is None:
        logger.info("webhook_unknown_message", extra={"message_id": message_id[:12]})
        return {"status": "ignored"}

    row.status = delivery_status
    if delivery_status is NotificationStatus.SENT:
        row.sent_at = utcnow()
    elif delivery_status is NotificationStatus.DELIVERED:
        row.sent_at = row.sent_at or utcnow()
        row.delivered_at = utcnow()
    db.commit()
    logger.info(
        "webhook_status_updated",
        extra={"notification_id": row.id, "status": str(delivery_status)},
    )
    return {"status": "updated"}
