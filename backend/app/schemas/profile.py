"""Profile and consent schemas (AGENTS.md section 6.1)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.enums import EducationLevel, Gender, Language, MaritalStatus
from app.reference.locations import districts_for, is_known_state
from app.schemas.validators import (
    ValidationMessage,
    is_valid_pincode,
    validate_dob,
)

POLICY_VERSION = "2026-10-01"


class ProfileBase(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    dob: date
    gender: Gender
    occupation: str | None = Field(default=None, max_length=100)
    annual_income: int = Field(ge=0, le=100_000_000)
    is_disabled: bool | None = None
    education: EducationLevel | None = None
    marital_status: MaritalStatus | None = None

    state: str = Field(min_length=2, max_length=100)
    district: str = Field(min_length=2, max_length=100)
    locality: str | None = Field(default=None, max_length=150)
    pincode: str = Field(min_length=6, max_length=6)
    language: Language = Language.ENGLISH

    @field_validator("dob")
    @classmethod
    def _dob_sensible(cls, value: date) -> date:
        return validate_dob(value) or value

    @field_validator("pincode")
    @classmethod
    def _pincode_format(cls, value: str) -> str:
        if not is_valid_pincode(value):
            raise ValueError(ValidationMessage.PINCODE)
        return value

    @field_validator("state")
    @classmethod
    def _state_known(cls, value: str) -> str:
        if not is_known_state(value):
            raise ValueError("Select a state from the list.")
        return value

    @field_validator("district")
    @classmethod
    def _district_known(cls, value: str, info: ValidationInfo) -> str:
        state = info.data.get("state")
        known = districts_for(state) if state else ()
        if known and value not in known:
            raise ValueError("Select a district from the list.")
        return value


class ProfileUpdateIn(ProfileBase):
    """Full profile update. PUT /me replaces every editable field."""

    data_processing_consent: bool | None = None
    whatsapp_opt_in: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mobile: str
    name: str | None
    dob: date | None
    gender: Gender | None
    occupation: str | None
    annual_income: int | None
    is_disabled: bool | None
    education: EducationLevel | None
    marital_status: MaritalStatus | None
    state: str | None
    district: str | None
    locality: str | None
    pincode: str | None
    language: Language

    consent_data_processing: bool
    consent_whatsapp: bool
    consent_version: str | None
    consented_at: datetime | None
    whatsapp_opted_out_at: datetime | None

    profile_complete: bool
    age: int | None
    is_senior: bool
    created_at: datetime


class DeleteAccountIn(BaseModel):
    confirm: str = Field(description="Type DELETE to confirm account removal")

    @field_validator("confirm")
    @classmethod
    def _must_be_delete(cls, value: str) -> str:
        if value.strip().upper() != "DELETE":
            raise ValueError("Type DELETE to confirm.")
        return value
