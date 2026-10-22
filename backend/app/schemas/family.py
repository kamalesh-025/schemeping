"""Family member schemas (AGENTS.md section 6.2)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EducationLevel, Gender, Relationship
from app.schemas.validators import validate_dob


class FamilyMemberBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    relationship: Relationship
    dob: date | None = None
    gender: Gender | None = None
    occupation: str | None = Field(default=None, max_length=100)
    education_status: EducationLevel | None = None
    annual_income: int | None = Field(default=None, ge=0, le=100_000_000)
    is_disabled: bool = False
    is_student: bool = False
    is_widow: bool = False

    @field_validator("dob")
    @classmethod
    def _dob_sensible(cls, value: date | None) -> date | None:
        return validate_dob(value)

    @field_validator("relationship")
    @classmethod
    def _not_self(cls, value: Relationship) -> Relationship:
        if value == Relationship.SELF:
            raise ValueError("A family member cannot have the relationship 'self'.")
        return value


class FamilyMemberCreateIn(FamilyMemberBase):
    pass


class FamilyMemberUpdateIn(BaseModel):
    """Partial update: only provided fields change."""

    name: str | None = Field(default=None, min_length=2, max_length=150)
    relationship: Relationship | None = None
    dob: date | None = None
    gender: Gender | None = None
    occupation: str | None = Field(default=None, max_length=100)
    education_status: EducationLevel | None = None
    annual_income: int | None = Field(default=None, ge=0, le=100_000_000)
    is_disabled: bool | None = None
    is_student: bool | None = None
    is_widow: bool | None = None

    @field_validator("dob")
    @classmethod
    def _dob_sensible(cls, value: date | None) -> date | None:
        return validate_dob(value)

    @field_validator("relationship")
    @classmethod
    def _not_self(cls, value: Relationship | None) -> Relationship | None:
        if value == Relationship.SELF:
            raise ValueError("A family member cannot have the relationship 'self'.")
        return value


class FamilyMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    relationship: Relationship
    dob: date | None
    gender: Gender | None
    occupation: str | None
    education_status: EducationLevel | None
    annual_income: int | None
    is_disabled: bool | None
    is_student: bool
    is_widow: bool

    # Derived server-side from dob; never accepted from the client.
    age: int | None
    is_senior: bool
    is_minor: bool

    created_at: datetime
    updated_at: datetime
