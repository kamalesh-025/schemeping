"""Lightweight analytics events (Phase 6 Part C).

The app records what a citizen looks at - a scheme opened, an apply guide
followed - so the team can see which schemes matter. No cookies, no
third-party scripts: one row per event, no personal data beyond the
already-known user id.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.ratelimit import enforce
from app.models.analytics import AnalyticsEvent

router = APIRouter(tags=["analytics"])

EventKind = Literal["scheme_view", "apply_click", "whatsapp_send", "chat_question"]


class EventIn(BaseModel):
    kind: EventKind
    scheme_id: int | None = Field(default=None, ge=1)


class EventOut(BaseModel):
    recorded: bool
    kind: str


@router.post("/events", response_model=EventOut)
def record_event(
    payload: EventIn, request: Request, user: CurrentUser, db: DbSession
) -> EventOut:
    # Events are cheap but pointless in bulk: 60/minute per IP is plenty.
    enforce(request, limit=60, window_seconds=60, scope="events")
    db.add(
        AnalyticsEvent(
            user_id=user.id,
            scheme_id=payload.scheme_id,
            kind=payload.kind,
        )
    )
    db.commit()
    return EventOut(recorded=True, kind=payload.kind)
