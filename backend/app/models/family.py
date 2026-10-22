"""Family member belonging to a registered user."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as orm_relationship

from app.models.base import Base, TimestampMixin, utcnow
from app.models.enums import EducationLevel
from app.models.enums import Relationship as RelationshipKind
from app.models.types import EncryptedString, enum_type

if TYPE_CHECKING:
    from app.models.eligibility import EligibilityResult
    from app.models.user import User


class FamilyMember(TimestampMixin, Base):
    __tablename__ = "family_members"
    __table_args__ = (Index("ix_family_members_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    relationship: Mapped[RelationshipKind] = mapped_column(
        enum_type(RelationshipKind), nullable=False
    )

    # Encrypted at rest (DPDP).
    dob: Mapped[date | None] = mapped_column(EncryptedString, nullable=True)
    gender: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    annual_income: Mapped[int | None] = mapped_column(EncryptedString, nullable=True)
    is_disabled: Mapped[bool | None] = mapped_column(EncryptedString, nullable=True)

    occupation: Mapped[str | None] = mapped_column(String(100))
    education_status: Mapped[EducationLevel | None] = mapped_column(
        enum_type(EducationLevel)
    )

    is_student: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_widow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Derived from dob by the daily job, never typed by the user.
    is_senior: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = orm_relationship(back_populates="family_members")
    eligibility_results: Mapped[list[EligibilityResult]] = orm_relationship(
        back_populates="family_member", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FamilyMember id={self.id} user_id={self.user_id}>"

    @property
    def age(self) -> int | None:
        if self.dob is None:
            return None
        today = utcnow().date()
        return (
            today.year
            - self.dob.year
            - ((today.month, today.day) < (self.dob.month, self.dob.day))
        )
