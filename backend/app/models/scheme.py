"""Schemes and their cached, LLM-generated translations."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import BenefitType, Language, SchemeLevel, SchemeScope, SchemeStatus
from app.models.types import enum_type

if TYPE_CHECKING:
    from app.models.eligibility import EligibilityResult


class Scheme(TimestampMixin, Base):
    __tablename__ = "schemes"
    __table_args__ = (
        Index("ix_schemes_status_category", "status", "category"),
        Index("ix_schemes_slug", "slug", unique=True),
        Index("ix_schemes_level_state", "level", "state"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    slug: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(250), nullable=False)
    department: Mapped[str] = mapped_column(String(250), nullable=False)

    level: Mapped[SchemeLevel] = mapped_column(
        enum_type(SchemeLevel), nullable=False
    )
    state: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[SchemeScope] = mapped_column(
        enum_type(SchemeScope), nullable=False
    )

    benefit_summary: Mapped[str] = mapped_column(Text, nullable=False)
    benefit_amount: Mapped[str | None] = mapped_column(String(150))
    benefit_type: Mapped[BenefitType] = mapped_column(
        enum_type(BenefitType), nullable=False
    )

    eligibility_rules: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    required_documents: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    application_steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)

    apply_url: Mapped[str | None] = mapped_column(String(500))
    deadline: Mapped[date | None] = mapped_column(Date)

    status: Mapped[SchemeStatus] = mapped_column(
        enum_type(SchemeStatus),
        default=SchemeStatus.DRAFT,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    last_verified_on: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)

    translations: Mapped[list[SchemeTranslation]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan"
    )
    eligibility_results: Mapped[list[EligibilityResult]] = relationship(
        back_populates="scheme", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Scheme id={self.id} slug={self.slug!r} status={self.status}>"


class SchemeTranslation(TimestampMixin, Base):
    """Cached LLM output. Regenerated only when the scheme changes."""

    __tablename__ = "scheme_translations"
    __table_args__ = (
        UniqueConstraint("scheme_id", "language", name="uq_scheme_translations_scheme_language"),
        Index("ix_scheme_translations_scheme_id", "scheme_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scheme_id: Mapped[int] = mapped_column(
        ForeignKey("schemes.id", ondelete="CASCADE"), nullable=False
    )

    language: Mapped[Language] = mapped_column(
        enum_type(Language), nullable=False
    )
    simple_title: Mapped[str] = mapped_column(String(250), nullable=False)
    simple_description: Mapped[str] = mapped_column(Text, nullable=False)
    simple_benefits: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    simple_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    generated_by: Mapped[str | None] = mapped_column(String(64))
    model_name: Mapped[str | None] = mapped_column(String(100))
    source_hash: Mapped[str | None] = mapped_column(String(64))

    scheme: Mapped[Scheme] = relationship(back_populates="translations")

    def __repr__(self) -> str:
        return f"<SchemeTranslation scheme_id={self.scheme_id} language={self.language}>"
