"""Computed eligibility results (written by the Phase 3 engine)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, utcnow
from app.models.enums import EligibilityStatus
from app.models.types import enum_type

if TYPE_CHECKING:
    from app.models.family import FamilyMember
    from app.models.scheme import Scheme
    from app.models.user import User


class EligibilityResult(Base):
    __tablename__ = "eligibility_results"
    __table_args__ = (
        Index("ix_eligibility_results_user_scheme", "user_id", "scheme_id"),
        Index("ix_eligibility_results_scheme_status", "scheme_id", "status"),
        UniqueConstraint(
            "user_id",
            "family_member_id",
            "scheme_id",
            name="uq_eligibility_results_person_scheme",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("family_members.id", ondelete="CASCADE")
    )
    scheme_id: Mapped[int] = mapped_column(
        ForeignKey("schemes.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[EligibilityStatus] = mapped_column(
        enum_type(EligibilityStatus), nullable=False
    )
    reasons: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    missing_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    user: Mapped[User] = relationship(back_populates="eligibility_results")
    family_member: Mapped[FamilyMember | None] = relationship(
        back_populates="eligibility_results"
    )
    scheme: Mapped[Scheme] = relationship(back_populates="eligibility_results")

    def __repr__(self) -> str:
        return (
            f"<EligibilityResult user_id={self.user_id} "
            f"family_member_id={self.family_member_id} scheme_id={self.scheme_id} "
            f"status={self.status}>"
        )
