"""Registered user (head of household)."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, utcnow
from app.models.enums import EducationLevel, Language, MaritalStatus
from app.models.types import EncryptedString, enum_type
from app.services.notification_prefs import default_notification_prefs

if TYPE_CHECKING:
    from app.models.chat import ChatMessage
    from app.models.eligibility import EligibilityResult
    from app.models.family import FamilyMember
    from app.models.notification import Notification
    from app.models.refresh_token import RefreshToken


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_mobile", "mobile", unique=True),
        Index("ix_users_state_district", "state", "district"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str | None] = mapped_column(String(150))
    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    mobile_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # scrypt hash (see core.security). NULL for accounts created by an OTP flow;
    # an operator sets one with app/scripts/reset_password.py.
    password_hash: Mapped[str | None] = mapped_column(String(255))

    # Encrypted at rest (DPDP): date of birth, income and gender are sensitive.
    dob: Mapped[date | None] = mapped_column(EncryptedString, nullable=True)
    gender: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
    annual_income: Mapped[int | None] = mapped_column(EncryptedString, nullable=True)
    is_disabled: Mapped[bool | None] = mapped_column(EncryptedString, nullable=True)

    occupation: Mapped[str | None] = mapped_column(String(100))
    education: Mapped[EducationLevel | None] = mapped_column(
        enum_type(EducationLevel)
    )
    marital_status: Mapped[MaritalStatus | None] = mapped_column(
        enum_type(MaritalStatus)
    )

    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    locality: Mapped[str | None] = mapped_column(String(150))
    pincode: Mapped[str | None] = mapped_column(String(10))

    language: Mapped[Language] = mapped_column(
        enum_type(Language), default=Language.ENGLISH, nullable=False
    )

    # Consent records (what, when, which policy version).
    consent_data_processing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_whatsapp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consent_version: Mapped[str | None] = mapped_column(String(32))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    whatsapp_opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Per-category notification toggles (see notification_prefs). Stored as
    # JSON so a new category defaults to on without a migration; NULL at the
    # SQL level means all-on (MySQL has no plain JSON column default).
    notification_prefs: Mapped[dict[str, bool] | None] = mapped_column(
        JSON, nullable=True, default=default_notification_prefs
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    family_members: Mapped[list[FamilyMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    eligibility_results: Mapped[list[EligibilityResult]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id}>"

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
