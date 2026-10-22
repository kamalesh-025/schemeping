"""Table-driven tests for the deterministic "why you qualify" sentences."""

from __future__ import annotations

import pytest
from app.eligibility.explain import explain_facts

ELIGIBLE = "eligible"
NOT_ELIGIBLE = "not_eligible"
NEEDS_INFO = "needs_info"


@pytest.mark.parametrize(
    ("status", "reasons", "missing", "expected"),
    [
        (
            ELIGIBLE,
            [
                {
                    "field": "state",
                    "ok": True,
                    "user_value": "Tamil Nadu",
                    "required": "state == Tamil Nadu",
                },
                {"field": "age", "ok": True, "user_value": 40, "required": "age >= 30"},
            ],
            [],
            ["You qualify: State is Tamil Nadu.", "You qualify: Age >= 30."],
        ),
        (
            ELIGIBLE,
            [
                {
                    "field": "annual_income",
                    "ok": True,
                    "user_value": 60000,
                    "required": "annual_income <= 250000",
                }
            ],
            [],
            ["You qualify: Annual income <= ₹250000."],
        ),
        (ELIGIBLE, [], [], ["You qualify for this scheme."]),
        (
            ELIGIBLE,
            [{"field": "age", "ok": False, "user_value": 10, "required": "age >= 30"}],
            [],
            ["You qualify for this scheme."],
        ),
        (
            NOT_ELIGIBLE,
            [
                {"field": "age", "ok": False, "user_value": 10, "required": "age >= 30"},
                {
                    "field": "state",
                    "ok": False,
                    "user_value": "Kerala",
                    "required": "state == Tamil Nadu",
                },
            ],
            [],
            ["Not eligible: Age must be >= 30.", "Not eligible: State must be Tamil Nadu."],
        ),
        (
            NOT_ELIGIBLE,
            [
                {
                    "field": "occupation",
                    "ok": False,
                    "user_value": "teacher",
                    "required": "occupation in ['farmer', 'agricultural_labourer']",
                },
            ],
            [],
            ["Not eligible: Occupation must be one of ['farmer', 'agricultural_labourer']."],
        ),
        (NOT_ELIGIBLE, [], [], ["Not eligible for this scheme."]),
        (
            NEEDS_INFO,
            [],
            ["annual_income", "dob"],
            ["Add Annual income to check this scheme.", "Add Date of birth to check this scheme."],
        ),
        (NEEDS_INFO, [], [], ["More information is needed to check this scheme."]),
        (
            NEEDS_INFO,
            [{"field": "age", "ok": True, "user_value": 40, "required": "age >= 30"}],
            ["household_income"],
            ["Add Household income to check this scheme."],
        ),
        # Unknown conditions carry ok None; they are filtered out everywhere.
        (
            ELIGIBLE,
            [
                {
                    "field": "gender",
                    "ok": True,
                    "user_value": "female",
                    "required": "gender == female",
                }
            ],
            [],
            ["You qualify: Gender is female."],
        ),
    ],
)
def test_explain_facts_templates(status, reasons, missing, expected):
    assert explain_facts(status, reasons, missing) == expected


def test_unknown_status_yields_needs_info_line():
    assert explain_facts("any_other_state", [], ["dob"]) == [
        "Add Date of birth to check this scheme."
    ]


def test_pure_no_state_leak_between_calls():
    first = explain_facts(
        ELIGIBLE,
        [
            {
                "field": "state",
                "ok": True,
                "user_value": "Tamil Nadu",
                "required": "state == Tamil Nadu",
            }
        ],
        [],
    )
    second = explain_facts(NEEDS_INFO, [], ["dob"])
    assert first == ["You qualify: State is Tamil Nadu."]
    assert second == ["Add Date of birth to check this scheme."]
