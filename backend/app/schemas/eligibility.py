"""Response schemas for the eligibility dashboard."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

EligibilityStatusLiteral = Literal["eligible", "needs_info", "not_eligible"]
ScopeLiteral = Literal["individual", "family", "event"]


class StatusCounts(BaseModel):
    eligible: int = 0
    needs_info: int = 0
    not_eligible: int = 0
    total: int = 0


class PersonSummary(BaseModel):
    """Counts for one person ("me" or one family member)."""

    kind: Literal["me", "family"]
    id: int | None
    name: str | None
    counts: StatusCounts
    by_category: dict[str, StatusCounts]


class SummaryOut(BaseModel):
    people: list[PersonSummary]


class EligibilityCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scheme_id: int
    slug: str
    name: str
    department: str
    level: str
    state: str | None
    category: str
    scope: str
    benefit_summary: str
    benefit_amount: str | None
    benefit_type: str
    status: EligibilityStatusLiteral
    deadline: date | None
    days_remaining: int | None
    priority: Literal["high", "medium", "normal"]
    reason_line: str
    missing_fields: list[str]
    last_verified_on: date


class CardsOut(BaseModel):
    total: int
    cards: list[EligibilityCardOut]


class RecomputeOut(BaseModel):
    people: int
    schemes: int
    created: int
    updated: int
    unchanged: int
