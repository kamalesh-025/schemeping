"""Derived person flags.

This is the single place where age, senior status, and minor status are
computed from a date of birth. Phase 3's eligibility engine and the daily
Celery job must call these helpers rather than re-deriving the logic, so that a
profile, a family member, and a background recomputation always agree.

Nothing here touches the database or the network: it is pure and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.core.time import age_on, utcnow

# Senior citizen threshold used by most Indian welfare schemes. Central
# schemes vary between 58 and 65; 60 is the statutory default (Maintenance and
# Welfare of Parents and Senior Citizens Act, 2007).
SENIOR_AGE = 60
MINOR_AGE = 18


class Profilable(Protocol):
    """Anything with the profile columns of ``users`` or ``family_members``."""

    dob: date | None
    name: str | None
    gender: str | None
    state: str | None
    district: str | None
    pincode: str | None
    annual_income: int | None


# A profile is "complete" when every field the eligibility engine needs is
# present. Occupation, education, and marital status stay optional because many
# schemes do not use them and requiring them adds friction for low-literacy
# users.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "name",
    "dob",
    "gender",
    "annual_income",
    "state",
    "district",
    "pincode",
)


def missing_profile_fields(person: Profilable) -> list[str]:
    missing: list[str] = []
    for field_name in REQUIRED_PROFILE_FIELDS:
        value = getattr(person, field_name, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field_name)
    return missing


def is_profile_complete(person: Profilable) -> bool:
    return not missing_profile_fields(person)



@dataclass(frozen=True)
class DerivedFlags:
    age: int | None
    is_senior: bool
    is_minor: bool
    is_adult: bool

    def as_dict(self) -> dict[str, int | bool | None]:
        return {
            "age": self.age,
            "is_senior": self.is_senior,
            "is_minor": self.is_minor,
            "is_adult": self.is_adult,
        }


def derive_flags(dob: date | None, *, today: date | None = None) -> DerivedFlags:
    """Compute all age-derived flags for one person.

    A missing date of birth yields ``age=None`` and every boolean ``False``,
    which the Phase 3 engine treats as ``needs_info`` rather than a guess.
    """
    if dob is None:
        return DerivedFlags(age=None, is_senior=False, is_minor=False, is_adult=False)

    reference = today or utcnow().date()
    age = age_on(dob, reference)
    return DerivedFlags(
        age=age,
        is_senior=age >= SENIOR_AGE,
        is_minor=age < MINOR_AGE,
        is_adult=age >= MINOR_AGE,
    )


def household_flags(
    incomes: list[int | None],
    *,
    ages: list[int | None] | None = None,
    genders: list[str | None] | None = None,
    relationships: list[str | None] | None = None,
    has_disabled_member: bool = False,
) -> dict[str, int | bool]:
    """Aggregate household fields used by ``scope=family`` schemes.

    ``household_income`` sums known incomes; unknown incomes are ignored so the
    engine sees a number rather than ``None``. Callers should still mark the
    result as partial when any income is unknown (Phase 3).
    """
    known_incomes = [income for income in incomes if income is not None]
    ages = ages or []
    genders = genders or []
    relationships = relationships or []

    known_ages = [age for age in ages if age is not None]
    has_girl_child = any(
        gender == "female" and age is not None and age < 18
        for gender, age in zip(genders, ages, strict=False)
    ) or any(
        relationship == "daughter" and (age is None or age < 18)
        for relationship, age in zip(relationships, ages, strict=False)
    )

    return {
        "household_income": sum(known_incomes),
        "family_size": len(incomes),
        "has_senior": any(age >= SENIOR_AGE for age in known_ages),
        "has_girl_child": has_girl_child,
        "has_disabled_member": has_disabled_member,
        "has_student": False,
    }
