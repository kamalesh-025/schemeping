"""Assistant endpoints: POST /chat and GET /chat/history.

Authentication is the standard cookie/bearer session. Rate limiting is
per user, enforced in the service; the endpoint maps it to HTTP 429.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, DbSession
from app.core.time import ensure_utc
from app.models.enums import ChatRole
from app.services import chat as chat_service
from app.services.chat import ChatRateLimited

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: Literal["en", "ta", "hi", "te", "kn", "ml"] | None = None


class SourceOut(BaseModel):
    id: int
    name: str


class ChatOut(BaseModel):
    answer: str
    sources: list[SourceOut]
    language: str
    grounded: bool


class HistoryItem(BaseModel):
    id: int
    role: ChatRole
    content: str
    language: str
    created_at: datetime


class ChatHistoryOut(BaseModel):
    total: int
    messages: list[HistoryItem]


@router.post("/chat", response_model=ChatOut)
def ask_assistant(payload: ChatIn, user: CurrentUser, db: DbSession) -> ChatOut:
    try:
        reply = chat_service.answer(db, user, payload.message, language=payload.language)
    except ChatRateLimited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You are sending too many questions. Please try again in a while.",
        ) from None
    return ChatOut(
        answer=reply.answer,
        sources=reply.sources,
        language=reply.language,
        grounded=reply.grounded,
    )


@router.get("/chat/history", response_model=ChatHistoryOut)
def chat_history(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> ChatHistoryOut:
    from sqlalchemy import select

    from app.models.chat import ChatMessage

    def enum_text(value: object) -> str:
        return str(getattr(value, "value", value))

    rows: Sequence[ChatMessage] = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == user.id)
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    ).all()
    return ChatHistoryOut(
        total=len(rows),
        messages=[
            HistoryItem(
                id=row.id,
                role=row.role,
                content=row.content,
                language=enum_text(row.language),
                created_at=ensure_utc(row.created_at),
            )
            for row in reversed(rows)
        ],
    )
