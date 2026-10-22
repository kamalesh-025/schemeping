"""Scheme definition schema and YAML loading for the seed pipeline.

Every seed file is validated with Pydantic **and** with the rule-structure
validator before anything is written to the database. A malformed rule file
aborts the whole run rather than silently loading a broken scheme.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from app.eligibility.rules import validate_eligibility_rules
from app.models.enums import BenefitType, Language, SchemeLevel, SchemeScope, SchemeStatus
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

SAMPLE_DATA_WARNING = "SAMPLE DATA, verify against the official source before publishing"

SCHEMES_DIR = Path(__file__).resolve().parent / "schemes"
FACILITIES_FILE = Path(__file__).resolve().parent / "facilities.yaml"


class SeedValidationError(ValueError):
    """Raised when a seed file is structurally invalid."""


class DocumentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=500)


class ApplicationStepSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)


class SchemeSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=150)
    name: str = Field(min_length=3, max_length=250)
    department: str = Field(min_length=3, max_length=250)

    level: SchemeLevel
    state: str | None = Field(default=None, max_length=100)
    category: str = Field(min_length=2, max_length=64)
    scope: SchemeScope

    benefit_summary: str = Field(min_length=10)
    benefit_amount: str | None = Field(default=None, max_length=150)
    benefit_type: BenefitType

    eligibility_rules: dict[str, Any]
    required_documents: list[DocumentSpec] = Field(min_length=1)
    application_steps: list[ApplicationStepSpec] = Field(min_length=1)

    apply_url: HttpUrl | None = None
    deadline: date | None = None

    status: SchemeStatus = SchemeStatus.DRAFT
    priority: int = Field(default=100, ge=0, le=1000)

    last_verified_on: date
    source_url: HttpUrl

    @field_validator("eligibility_rules")
    @classmethod
    def _rules_are_well_formed(cls, value: dict[str, Any]) -> dict[str, Any]:
        return validate_eligibility_rules(value)

    @field_validator("state")
    @classmethod
    def _state_required_for_state_schemes(cls, value: str | None, info: Any) -> str | None:
        level = info.data.get("level")
        if level == SchemeLevel.STATE and not value:
            raise ValueError("state is required when level is 'state'")
        return value

    @field_validator("application_steps")
    @classmethod
    def _steps_are_ordered(
        cls, value: list[ApplicationStepSpec]
    ) -> list[ApplicationStepSpec]:
        orders = [step.order for step in value]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise ValueError("application_steps must be numbered 1..n without gaps or repeats")
        return sorted(value, key=lambda step: step.order)


class FacilitySeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_ref: str = Field(min_length=3, max_length=150)
    name: str = Field(min_length=3, max_length=250)
    type: Literal[
        "csc", "taluk_office", "collector_office", "e_sevai", "welfare_office"
    ]
    address: str = Field(min_length=5, max_length=500)
    district: str = Field(min_length=2, max_length=100)
    state: str = Field(min_length=2, max_length=100)
    pincode: str | None = Field(default=None, max_length=10)
    phone: str | None = Field(default=None, max_length=30)
    working_hours: str | None = Field(default=None, max_length=250)
    latitude: float = Field(ge=6.0, le=37.5, description="India latitude range")
    longitude: float = Field(ge=68.0, le=97.5, description="India longitude range")
    verified_on: date
    source_url: HttpUrl


def load_yaml(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise SeedValidationError(f"{path.name}: invalid YAML: {exc}") from exc


def load_scheme_files(directory: Path | None = None) -> list[SchemeSeed]:
    """Load and validate every ``*.yaml`` scheme file in ``directory``."""
    folder = directory or SCHEMES_DIR
    if not folder.is_dir():
        raise SeedValidationError(f"Scheme seed directory not found: {folder}")

    schemes: list[SchemeSeed] = []
    seen_slugs: set[str] = set()

    for path in sorted(folder.glob("*.yaml")):
        raw = load_yaml(path)
        if not isinstance(raw, dict):
            raise SeedValidationError(f"{path.name}: top level must be a mapping")
        try:
            scheme = SchemeSeed.model_validate(raw)
        except Exception as exc:
            raise SeedValidationError(f"{path.name}: {exc}") from exc

        if scheme.slug in seen_slugs:
            raise SeedValidationError(f"{path.name}: duplicate slug {scheme.slug!r}")
        seen_slugs.add(scheme.slug)
        schemes.append(scheme)

    if not schemes:
        raise SeedValidationError(f"No scheme seed files found in {folder}")
    return schemes


def load_facility_file(path: Path | None = None) -> list[FacilitySeed]:
    source = path or FACILITIES_FILE
    raw = load_yaml(source)
    if not isinstance(raw, list):
        raise SeedValidationError(f"{source.name}: top level must be a list")

    facilities: list[FacilitySeed] = []
    seen_refs: set[str] = set()
    for index, item in enumerate(raw):
        try:
            facility = FacilitySeed.model_validate(item)
        except Exception as exc:
            raise SeedValidationError(f"{source.name}[{index}]: {exc}") from exc
        if facility.external_ref in seen_refs:
            raise SeedValidationError(
                f"{source.name}: duplicate external_ref {facility.external_ref!r}"
            )
        seen_refs.add(facility.external_ref)
        facilities.append(facility)
    return facilities


def supported_languages() -> list[str]:
    return [language.value for language in Language]
