"""Lightweight UI event tracking for Metabase analytics (Phase 6 Part C).

One small append-only table: what users look at. No cookies, no third
parties; only the user id (when logged in), the scheme and the event kind.
Notification and eligibility statistics already live in their own tables.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow

if TYPE_CHECKING:
    from app.models.scheme import Scheme
    from app.models.user import User

EventKind = Literal["scheme_view", "apply_click", "whatsapp_send", "chat_question"]


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_kind_created", "kind", "created_at"),
        Index("ix_analytics_events_scheme", "scheme_id"),
        Index("ix_analytics_events_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    scheme_id: Mapped[int | None] = mapped_column(
        ForeignKey("schemes.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    user: Mapped[User | None] = relationship(viewonly=True, uselist=False)
    scheme: Mapped[Scheme | None] = relationship(viewonly=True, uselist=False)

    def __repr__(self) -> str:
        return f"<AnalyticsEvent id={self.id} kind={self.kind}>"
