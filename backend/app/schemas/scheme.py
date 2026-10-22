"""Pydantic response models for scheme detail and facilities."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LanguageLiteral = Literal["en", "ta", "hi", "te", "kn", "ml"]
StatusLiteral = Literal["eligible", "needs_info", "not_eligible"]

DocumentOut = dict[str, Any]


class TranslationOut(BaseModel):
    simple_title: str
    simple_description: str
    simple_benefits: list[str]
    simple_steps: list[str]
    cached: bool = False
    fallback: bool = False


class SchemeDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: int
    slug: str
    name: str
    department: str
    level: Literal["central", "state"]
    state: str | None
    category: str
    scope: Literal["individual", "family", "event"]
    benefit_summary: str
    benefit_amount: str | None
    benefit_type: str
    deadline: str | None
    days_remaining: int | None
    apply_url: str | None
    source_url: str
    last_verified_on: str | None
    required_documents: list[DocumentOut]
    application_steps: list[DocumentOut]
    eligibility_status: StatusLiteral
    why_qualify: list[str]
    missing_fields: list[str]
    person: str | int
    language: LanguageLiteral
    translation: TranslationOut | None


class FacilityOut(BaseModel):
    id: int
    name: str
    type: Literal["csc", "taluk_office", "collector_office", "e_sevai", "welfare_office"]
    address: str
    district: str
    state: str
    pincode: str | None
    phone: str | None
    working_hours: str | None
    lat: float | None
    lon: float | None
    distance_km: float | None = Field(
        description="Only set by the nearest endpoint, which sorts by it."
    )


class FacilitiesOut(BaseModel):
    total: int
    facilities: list[FacilityOut]
