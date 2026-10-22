"""Context builders for the eligibility engine.

The engine is pure and takes a flat dict of fields. This module turns a
person's profile (the ``users`` or ``family_members`` row, as plain data) into
that dict, plus the two aggregate contexts the other ``applies_to`` modes need:

- ``build_person_context``: one person, with age flags derived from DOB via
  ``app.services.profile.derive_flags`` (the single source for that logic).
- ``build_household_context``: the whole household for ``scope=family`` rules
  (``household_income``, ``family_size``, ``has_senior``, ``has_girl_child``,
  ``has_disabled_member``, ``has_student``).

Household aggregation is three-valued too: when any member's relevant input is
unknown (for example a missing date of birth), the aggregate becomes unknown
and the engine reports ``needs_info`` rather than guessing. A household income
is only known when *every* member has one.

Pure module: no database, no network. Callers map ORM rows to the dataclasses
in ``app.services.eligibility``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.services.profile import derive_flags


@dataclass(frozen=True)
class PersonProfile:
    """Plain-data view of one person (a user row or a family member row)."""

    name: str | None = None
    dob: date | None = None
    gender: str | None = None
    annual_income: int | None = None
    occupation: str | None = None
    education: str | None = None
    education_status: str | None = None
    marital_status: str | None = None
    relationship: str | None = None
    state: str | None = None
    district: str | None = None
    pincode: str | None = None
    is_student: bool | None = None
    is_disabled: bool | None = None
    is_widow: bool | None = None


def _set_if_known(context: dict[str, Any], key: str, value: Any) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return
    context[key] = value


def _student_value(profile: PersonProfile) -> bool | None:
    """Student status: explicit for family members, derived for the user.

    Users do not have an ``is_student`` column; a profile whose occupation is
    ``student`` counts, anything else is genuinely unknown.
    """
    if profile.is_student is not None:
        return profile.is_student
    if profile.occupation is not None and profile.occupation.strip().lower() == "student":
        return True
    return None


def _widow_value(profile: PersonProfile) -> bool | None:
    """Widow status: explicit column for members, derived from marital status."""
    if profile.is_widow is not None:
        return profile.is_widow
    if profile.marital_status is None:
        return None
    return profile.marital_status == "widowed"


def build_person_context(profile: PersonProfile) -> dict[str, Any]:
    """Build the engine context for one individual.

    Only known values are included; the engine treats a missing key as unknown
    so every rule on an unknown field yields ``needs_info`` with that field
    listed, never a guess.
    """
    flags = derive_flags(profile.dob)
    context: dict[str, Any] = {}

    if flags.age is not None:
        context["age"] = flags.age
        context["is_senior"] = flags.is_senior
        context["is_minor"] = flags.is_minor

    for key, value in (
        ("gender", profile.gender),
        ("annual_income", profile.annual_income),
        ("occupation", profile.occupation),
        ("education", profile.education),
        ("education_status", profile.education_status or profile.education),
        ("marital_status", profile.marital_status),
        ("relationship", profile.relationship),
        ("state", profile.state),
        ("district", profile.district),
        ("pincode", profile.pincode),
    ):
        _set_if_known(context, key, value)

    for key, value in (
        ("is_student", _student_value(profile)),
        ("is_disabled", profile.is_disabled),
        ("is_widow", _widow_value(profile)),
    ):
        _set_if_known(context, key, value)

    return context


def _combine_or(values: list[bool | None]) -> bool | None:
    """Any definite True wins; some unknowns make the aggregate unknown."""
    if True in values:
        return True
    if None in values:
        return None
    return False


def build_household_context(
    head: PersonProfile, members: list[PersonProfile]
) -> dict[str, Any]:
    """Build the engine context for the household (head plus family members).

    Aggregates are unknown until every input they need is present, so an
    incomplete family member makes income-based family rules ``needs_info``
    instead of quietly understating the household income.
    """
    people = [head, *members]
    contexts = [build_person_context(person) for person in people]

    context: dict[str, Any] = {}
    for key in ("state", "district", "pincode"):
        _set_if_known(context, key, getattr(head, key))

    incomes = [person.annual_income for person in people]
    known_incomes = [income for income in incomes if income is not None]
    if len(known_incomes) == len(incomes):
        context["household_income"] = sum(known_incomes)
    context["family_size"] = len(people)

    senior_values: list[bool | None] = [
        context_member.get("is_senior", None) for context_member in contexts
    ]
    context["has_senior"] = _combine_or(senior_values)

    # A girl child: female and (known to be) a minor. Unknown gender or age
    # keeps the aggregate honest instead of defaulting to False.
    girl_values: list[bool | None] = []
    for person, context_member in zip(people, contexts, strict=True):
        if person.gender != "female":
            girl_values.append(False)
        elif "is_minor" in context_member:
            girl_values.append(context_member["is_minor"])
        else:
            girl_values.append(None)
    context["has_girl_child"] = _combine_or(girl_values)

    context["has_disabled_member"] = _combine_or(
        [person.is_disabled for person in people]
    )
    context["has_student"] = _combine_or(
        [_student_value(person) for person in people]
    )

    return context
