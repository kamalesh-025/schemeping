"""Table-driven tests for the eligibility engine: operators and leaves.

Every operator of AGENTS.md §8.1 must behave the same way every time, and an
unknown field must produce ``needs_info`` — never ``eligible``, never a guess.
Boundary values (age 18 exactly, income exactly at the limit) are explicit.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.eligibility.engine import (
    ELIGIBLE,
    NEEDS_INFO,
    NOT_ELIGIBLE,
    EligibilityOutcome,
    Reason,
    evaluate,
)
from app.eligibility.rules import RuleValidationError


def _rules(tree: Any) -> dict[str, Any]:
    return {"applies_to": "individual", "rules": tree}


def _cond(field: str, op: str, value: Any) -> dict[str, Any]:
    return {"field": field, "op": op, "value": value}


# --------------------------------------------------------------- comparisons


@pytest.mark.parametrize(
    ("field_name", "op", "value", "context", "expected"),
    [
        ("age", "==", 18, {"age": 18}, ELIGIBLE),  # exact
        ("age", "==", 18, {"age": 19}, NOT_ELIGIBLE),
        ("state", "==", "Tamil Nadu", {"state": "Tamil Nadu"}, ELIGIBLE),
        ("state", "==", "Tamil Nadu", {"state": "Karnataka"}, NOT_ELIGIBLE),
        ("is_disabled", "==", True, {"is_disabled": True}, ELIGIBLE),
        ("is_disabled", "==", True, {"is_disabled": False}, NOT_ELIGIBLE),
        ("occupation", "!=", "farmer", {"occupation": "weaver"}, ELIGIBLE),
        ("occupation", "!=", "farmer", {"occupation": "farmer"}, NOT_ELIGIBLE),
        ("age", "<", 60, {"age": 59}, ELIGIBLE),
        ("age", "<", 60, {"age": 60}, NOT_ELIGIBLE),  # boundary
        ("annual_income", "<=", 250000, {"annual_income": 250000}, ELIGIBLE),  # boundary
        ("annual_income", "<=", 250000, {"annual_income": 250001}, NOT_ELIGIBLE),
        ("age", ">", 17, {"age": 18}, ELIGIBLE),  # boundary: age 18
        ("age", ">", 18, {"age": 18}, NOT_ELIGIBLE),
        ("age", ">=", 60, {"age": 60}, ELIGIBLE),  # senior boundary
        ("age", ">=", 60, {"age": 59}, NOT_ELIGIBLE),
    ],
)
def test_scalar_operators(
    field_name: str, op: str, value: Any, context: dict, expected: str
) -> None:
    outcome = evaluate(
        _rules({"all": [_cond(field_name, op, value)]}), context
    )
    assert outcome.status == expected


@pytest.mark.parametrize(
    ("field_name", "op", "value", "context", "expected"),
    [
        (
            "occupation",
            "in",
            ["farmer", "agricultural_labourer"],
            {"occupation": "farmer"},
            ELIGIBLE,
        ),
        ("occupation", "in", ["farmer"], {"occupation": "weaver"}, NOT_ELIGIBLE),
        ("state", "in", ["Tamil Nadu", "Kerala"], {"state": "Tamil Nadu"}, ELIGIBLE),
        ("state", "not_in", ["Karnataka"], {"state": "Tamil Nadu"}, ELIGIBLE),
        ("state", "not_in", ["Tamil Nadu"], {"state": "Tamil Nadu"}, NOT_ELIGIBLE),
        ("occupation", "not_in", ["weaver"], {"occupation": "farmer"}, ELIGIBLE),
    ],
)
def test_membership_operators(field_name, op, value, context, expected) -> None:
    outcome = evaluate(_rules({"all": [_cond(field_name, op, value)]}), context)
    assert outcome.status == expected


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        ({"annual_income": 100000}, ELIGIBLE),  # inside
        ({"annual_income": 250000}, ELIGIBLE),  # at high bound
        ({"annual_income": 0}, ELIGIBLE),  # at low bound
        ({"annual_income": 250001}, NOT_ELIGIBLE),
        ({"annual_income": -1}, NOT_ELIGIBLE),
    ],
)
def test_between(context: dict, expected: str) -> None:
    outcome = evaluate(
        _rules({"all": [{"field": "annual_income", "op": "between", "value": [0, 250000]}]}),
        context,
    )
    assert outcome.status == expected


# ------------------------------------------------------------------- unknown


@pytest.mark.parametrize(
    ("tree", "expected_missing"),
    [
        (_cond("age", ">=", 18), ["age"]),
        (_cond("annual_income", "<=", 250000), ["annual_income"]),
        (_cond("gender", "==", "female"), ["gender"]),
        (_cond("is_disabled", "exists", True), ["is_disabled"]),
    ],
)
def test_missing_field_is_needs_info(tree: dict, expected_missing: list) -> None:
    outcome = evaluate(_rules({"all": [tree]}), {})
    assert outcome.status == NEEDS_INFO
    assert list(outcome.missing_fields) == expected_missing


def test_empty_string_counts_as_missing() -> None:
    outcome = evaluate(_rules({"all": [_cond("state", "==", "Tamil Nadu")]}), {"state": "  "})
    assert outcome.status == NEEDS_INFO
    assert list(outcome.missing_fields) == ["state"]


def test_incomparable_value_fails_not_guesses() -> None:
    outcome = evaluate(
        _rules({"all": [_cond("annual_income", "<=", 250000)]}),
        {"annual_income": "not a number"},  # bad data beats the rule to it
    )
    assert outcome.status == NOT_ELIGIBLE
    failing = [reason for reason in outcome.reasons if not reason.ok]
    assert failing == [
        Reason(
            field="annual_income",
            ok=False,
            user_value="not a number",
            required="annual_income <= 250000",
        )
    ]


def test_exists_operator_known_values() -> None:
    # "exists" means the field was recorded: a present value (even False
    # for a boolean column) satisfies ``exists == true``.
    outcome = evaluate(
        _rules({"all": [_cond("is_disabled", "exists", True)]}), {"is_disabled": False}
    )
    assert outcome.status == ELIGIBLE

    outcome = evaluate(
        _rules({"all": [_cond("is_disabled", "exists", False)]}), {"is_disabled": False}
    )
    assert outcome.status == NOT_ELIGIBLE


def test_reasons_carry_expected_fields() -> None:
    outcome = evaluate(_rules({"all": [_cond("age", ">=", 18)]}), {"age": 44})
    assert outcome.reasons == (Reason(field="age", ok=True, user_value=44, required="age >= 18"),)
    assert outcome.missing_fields == ()


def test_outcome_roundtrip_serialisation() -> None:
    outcome = evaluate(_rules({"all": [_cond("age", ">=", 18)]}), {})
    restored = EligibilityOutcome.from_dict(outcome.as_dict())
    assert restored == outcome


# ---------------------------------------------------------------- determinism


def test_same_input_same_output() -> None:
    tree = _rules(
        {
            "all": [
                _cond("age", ">=", 18),
                {
                    "any": [
                        _cond("is_student", "==", True),
                        _cond("occupation", "in", ["farmer"]),
                    ]
                },
            ]
        }
    )
    context = {"age": 30, "is_student": False, "occupation": "farmer"}
    first = evaluate(tree, context)
    second = evaluate(tree, context)
    assert first == second


def test_validation_defence_inside_engine() -> None:
    with pytest.raises(RuleValidationError):
        evaluate(_rules(_cond("age", "%%%", 5)), {"age": 5})
    with pytest.raises(RuleValidationError):
        evaluate(_rules(_cond("not_a_field", "==", 5)), {"not_a_field": 5})
