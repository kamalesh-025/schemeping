"""Table-driven tests for the eligibility rule structure validator.

The engine itself is Phase 3; this only proves malformed rules cannot be
loaded, which is what keeps a typo from silently marking citizens ineligible.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from app.eligibility.rules import (
    RuleValidationError,
    iter_conditions,
    validate_eligibility_rules,
)

VALID_RULES: list[dict[str, Any]] = [
    {
        "applies_to": "individual",
        "rules": {
            "all": [
                {"field": "age", "op": ">=", "value": 18},
                {"field": "annual_income", "op": "<=", "value": 250000},
                {"field": "state", "op": "==", "value": "Tamil Nadu"},
            ]
        },
    },
    {
        "applies_to": "individual",
        "rules": {
            "all": [
                {"field": "age", "op": ">=", "value": 18},
                {
                    "any": [
                        {"field": "is_student", "op": "==", "value": True},
                        {
                            "field": "occupation",
                            "op": "in",
                            "value": ["farmer", "agricultural_labourer"],
                        },
                    ]
                },
            ]
        },
    },
    {
        "applies_to": "family",
        "rules": {
            "all": [
                {"field": "household_income", "op": "between", "value": [0, 300000]},
                {"field": "family_size", "op": ">=", "value": 1},
                {"not": {"field": "has_senior", "op": "exists", "value": False}},
            ]
        },
    },
]


@pytest.mark.parametrize("rules", VALID_RULES)
def test_valid_rule_trees_are_accepted(rules: dict[str, Any]) -> None:
    assert validate_eligibility_rules(rules) is rules


@pytest.mark.parametrize(
    ("rules", "expected"),
    [
        (None, "must be an object"),
        ([], "must be an object"),
        ({"rules": {"all": []}}, "applies_to is required"),
        ({"applies_to": "household", "rules": {"all": []}}, "applies_to must be one of"),
        ({"applies_to": "individual"}, "rules must be an object"),
        ({"applies_to": "individual", "rules": {}}, "missing 'field'"),
        (
            {"applies_to": "individual", "rules": {"all": []}},
            "must not be empty",
        ),
        (
            {"applies_to": "individual", "rules": {"all": [{"op": "==", "value": 1}]}},
            "missing 'field'",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "agee", "op": ">=", "value": 18}]},
            },
            "unknown field",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "age", "op": "~=", "value": 18}]},
            },
            "unsupported operator",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "age", "op": ">="}]},
            },
            "missing 'value'",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "state", "op": "in", "value": []}]},
            },
            "needs a non-empty list",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {
                    "all": [{"field": "annual_income", "op": "between", "value": [5]}]
                },
            },
            "needs [low, high]",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {
                    "all": [
                        {"field": "annual_income", "op": "between", "value": [9, 1]}
                    ]
                },
            },
            "bounds are reversed",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "age", "op": "exists", "value": "yes"}]},
            },
            "'exists' needs a boolean",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {"all": [{"field": "age", "op": "==", "value": [1, 2]}]},
            },
            "needs a scalar value",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {
                    "all": [
                        {"field": "age", "op": ">=", "value": 1},
                        {"any": [{"field": "age", "op": "<=", "value": 9}]},
                    ],
                    "not": {"field": "age", "op": "==", "value": 5},
                },
            },
            "only one of all/any/not",
        ),
        (
            {
                "applies_to": "individual",
                "rules": {
                    "all": [{"field": "age", "op": ">=", "value": 1}],
                    "field": "age",
                },
            },
            "cannot also be a condition",
        ),
    ],
)
def test_malformed_rule_trees_are_rejected(
    rules: Any, expected: str
) -> None:
    with pytest.raises(RuleValidationError, match=re.escape(expected)):
        validate_eligibility_rules(rules)


def test_nesting_limit_is_enforced() -> None:
    node: dict[str, Any] = {"field": "age", "op": ">=", "value": 18}
    for _ in range(13):
        node = {"all": [node]}

    with pytest.raises(RuleValidationError, match="too deep"):
        validate_eligibility_rules({"applies_to": "individual", "rules": node})


def test_iter_conditions_flattens_every_branch() -> None:
    rules = VALID_RULES[1]
    conditions = iter_conditions(rules["rules"])

    assert [condition["field"] for condition in conditions] == [
        "age",
        "is_student",
        "occupation",
    ]
