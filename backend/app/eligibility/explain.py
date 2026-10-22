"""Human-readable one-line explanations for eligibility outcomes.

The engine produces structured reasons; this module turns them into the short
``reason_line`` shown on a scheme card ("Why you qualify"). The text is the
English data-layer wording; translating it into the app languages is the LLM's
job in Phase 4, so no formatting logic needs to be duplicated here.

Rendering rules:

- qualifying facts read positively ("Age >= 30", "State is Tamil Nadu");
- failed facts read as requirements ("Occupation must be one of [farmer]").

Pure module: no database, no network, no model calls.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.eligibility.engine import ELIGIBLE, NOT_ELIGIBLE, Reason

# Friendly labels. Anything not listed falls back to the raw field name.
FIELD_LABELS: Mapping[str, str] = {
    "age": "Age",
    "dob": "Date of birth",
    "annual_income": "Annual income",
    "household_income": "Household income",
    "gender": "Gender",
    "state": "State",
    "district": "District",
    "is_student": "Student status",
    "is_disabled": "Disability status",
    "is_widow": "Widow status",
    "is_senior": "Senior citizen status",
    "occupation": "Occupation",
    "relationship": "Relationship",
    "education": "Education",
    "education_status": "Education",
    "marital_status": "Marital status",
    "family_size": "Family size",
    "has_senior": "Household has a senior citizen",
    "has_girl_child": "Household has a girl child",
    "has_disabled_member": "Household has a disabled member",
}

_OPS = frozenset({"==", "!=", "<", "<=", ">", ">=", "in", "not_in", "between", "exists"})
_MONEY_FIELDS = frozenset({"annual_income", "household_income"})


def _label(field_name: str) -> str:
    return FIELD_LABELS.get(field_name, field_name.replace("_", " ").capitalize())


def _money(text: str, field_name: str) -> str:
    if field_name in _MONEY_FIELDS:
        return re.sub(r"\d+(?:\.\d+)?", r"₹\g<0>", text)
    return text


def _fact_text(reason: Reason) -> str:
    """Split "field op value" and word the fact by outcome."""
    field_name = reason.field
    if reason.required.startswith(field_name):
        rest = reason.required[len(field_name) :].strip()
    else:
        rest = reason.required
    parts = rest.split(" ", 1)
    op = parts[0] if parts else ""
    value_text = parts[1] if len(parts) > 1 else ""
    value_text = _money(value_text, field_name)
    label = _label(field_name)

    if op == "==":
        return f"{label} is {value_text}" if reason.ok else f"{label} must be {value_text}"
    if op == "!=":
        return f"{label} is not {value_text}" if reason.ok else f"{label} must not be {value_text}"
    if op == "in":
        return (
            f"{label} is one of {value_text}"
            if reason.ok
            else f"{label} must be one of {value_text}"
        )
    if op == "not_in":
        return (
            f"{label} not in {value_text}" if reason.ok else f"{label} must not be in {value_text}"
        )
    if op == "exists":
        return f"{label} is recorded" if reason.ok else f"{label} must be recorded"
    if op == "between":
        return (
            f"{label} is between {value_text}"
            if reason.ok
            else f"{label} must be between {value_text}"
        )
    if op in _OPS:  # ordered comparisons keep the compact symbol
        return f"{label} {op} {value_text}" if reason.ok else f"{label} must be {op} {value_text}"
    # Unknown operator: show the raw rule text rather than invent wording.
    return f"{label}: {reason.required}"


def reason_line(
    status: str,
    reasons: list[dict[str, object]] | None,
    missing_fields: list[str] | None,
) -> str:
    """One short sentence for a scheme card, per outcome state.

    - eligible: lists the qualifying conditions.
    - not_eligible: lists the failed conditions.
    - needs_info: lists the missing fields.
    """
    if status == ELIGIBLE:
        facts = [_fact_text(Reason.from_dict(item)) for item in (reasons or []) if item.get("ok")]
        if facts:
            return "You qualify: " + "; ".join(facts) + "."
        return "You qualify for this scheme."

    if status == NOT_ELIGIBLE:
        facts = [
            _fact_text(Reason.from_dict(item)) for item in (reasons or []) if not item.get("ok")
        ]
        if facts:
            return "Not eligible: " + "; ".join(facts) + "."
        return "Not eligible for this scheme."

    labels = [_label(field_name) for field_name in (missing_fields or [])]
    if labels:
        return "More information needed: " + ", ".join(labels) + "."
    return "More information is needed to check this scheme."


def explain_facts(
    status: str,
    reasons: list[dict[str, object]] | None,
    missing_fields: list[str] | None,
) -> list[str]:
    """Bullet sentences for the scheme detail page.

    Deterministic template over engine reasons — never the LLM (AGENTS.md 8
    and 9). Per outcome:

    - eligible: one sentence per qualifying fact ("State is Tamil Nadu");
      a fully unexplained pass still yields one generic line, never empty.
    - not_eligible: one sentence per failed fact ("Annual income must be
      <= ₹250000"); generic line when the engine failed no specific rule.
    - needs_info: one sentence per missing field ("Add: Annual income");
      generic line when nothing is named.

    Pure module: no database, no network, no model calls.
    """
    if status == ELIGIBLE:
        facts = [
            _fact_text(Reason.from_dict(item))
            for item in (reasons or [])
            if item.get("ok") is True
        ]
        return [f"You qualify: {fact}." for fact in facts] or (
            ["You qualify for this scheme."]
        )

    if status == NOT_ELIGIBLE:
        facts = [
            _fact_text(Reason.from_dict(item))
            for item in (reasons or [])
            if item.get("ok") is False
        ]
        return [f"Not eligible: {fact}." for fact in facts] or (
            ["Not eligible for this scheme."]
        )

    labels = [_label(field_name) for field_name in (missing_fields or [])]
    return [f"Add {label} to check this scheme." for label in labels] or (
        ["More information is needed to check this scheme."]
    )
