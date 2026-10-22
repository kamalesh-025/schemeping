"""Group logic: nested ``all`` / ``any`` / ``not`` and outcome combination."""

from __future__ import annotations

from app.eligibility.engine import ELIGIBLE, NEEDS_INFO, NOT_ELIGIBLE, evaluate

from tests.test_engine_operators import _cond, _rules

ADULT_FARMER = {"age": 35, "occupation": "farmer", "is_student": False}
INCOME_LOW = {"annual_income": 100000}


def test_all_fails_when_any_condition_fails() -> None:
    tree = {"all": [_cond("age", ">=", 18), _cond("occupation", "==", "farmer")]}
    outcome = evaluate(_rules(tree), {"age": 35, "occupation": "weaver"})
    assert outcome.status == NOT_ELIGIBLE


def test_all_is_unknown_when_one_field_missing() -> None:
    tree = {"all": [_cond("age", ">=", 18), _cond("occupation", "==", "farmer")]}
    outcome = evaluate(_rules(tree), {"age": 35})
    assert outcome.status == NEEDS_INFO
    assert list(outcome.missing_fields) == ["occupation"]


def test_not_eligible_outranks_unknown() -> None:
    tree = {"all": [_cond("age", ">=", 18), _cond("occupation", "==", "farmer")]}
    outcome = evaluate(_rules(tree), {"age": 12})
    assert outcome.status == NOT_ELIGIBLE
    # The missing field is still reported alongside the failure.
    assert list(outcome.missing_fields) == ["occupation"]


def test_any_passes_on_a_single_true_branch() -> None:
    tree = {
        "any": [
            _cond("is_student", "==", True),
            _cond("occupation", "in", ["farmer", "weaver"]),
        ]
    }
    outcome = evaluate(_rules(tree), {"is_student": False, "occupation": "weaver"})
    assert outcome.status == ELIGIBLE


def test_any_is_unknown_when_some_branches_missing() -> None:
    tree = {
        "any": [
            _cond("is_student", "==", True),
            _cond("occupation", "in", ["farmer", "weaver"]),
        ]
    }
    outcome = evaluate(_rules(tree), {"is_student": False})
    assert outcome.status == NEEDS_INFO


def test_not_inverts_a_false_condition() -> None:
    tree = {"not": {"all": [_cond("household_income", ">", 720000)]}}
    outcome = evaluate(_rules(tree), {"household_income": 200000})
    assert outcome.status == ELIGIBLE


def test_not_treats_unknown_field_as_unknown() -> None:
    tree = {"not": {"all": [_cond("annual_income", ">", 720000)]}}
    outcome = evaluate(_rules(tree), {})
    assert outcome.status == NEEDS_INFO


def test_nested_any_inside_all_spec() -> None:
    # The exact example from AGENTS.md §8.1.
    tree = {
        "all": [
            _cond("age", ">=", 18),
            _cond("annual_income", "<=", 250000),
            _cond("state", "==", "Tamil Nadu"),
            {
                "any": [
                    _cond("is_student", "==", True),
                    _cond("occupation", "in", ["farmer", "agricultural_labourer"]),
                ]
            },
        ]
    }
    outcome = evaluate(_rules(tree), ADULT_FARMER | INCOME_LOW | {"state": "Tamil Nadu"})
    assert outcome.status == ELIGIBLE

    outcome = evaluate(
        _rules(tree), ADULT_FARMER | INCOME_LOW | {"state": "Tamil Nadu"} | {"age": 15}
    )
    assert outcome.status == NOT_ELIGIBLE


def test_not_group_inside_all() -> None:
    tree = {
        "all": [
            _cond("state", "==", "Tamil Nadu"),
            {"not": {"all": [_cond("age", ">", 60)]}},
        ]
    }
    outcome = evaluate(_rules(tree), {"state": "Tamil Nadu", "age": 40})
    assert outcome.status == ELIGIBLE
    outcome = evaluate(_rules(tree), {"state": "Tamil Nadu", "age": 65})
    assert outcome.status == NOT_ELIGIBLE


def test_deep_nesting() -> None:
    tree = {
        "all": [
            _cond("age", ">=", 18),
            {
                "any": [
                    {"not": {"all": [_cond("gender", "==", "female")]}},
                    _cond("is_widow", "==", True),
                ]
            },
        ]
    }
    outcome = evaluate(_rules(tree), {"age": 30, "gender": "male"})
    assert outcome.status == ELIGIBLE
    outcome = evaluate(_rules(tree), {"age": 30, "gender": "female"})
    assert outcome.status == NEEDS_INFO  # is_widow missing
    outcome = evaluate(_rules(tree), {"age": 30, "gender": "female", "is_widow": True})
    assert outcome.status == ELIGIBLE


def test_missing_fields_are_deduped_and_ordered() -> None:
    tree = {
        "all": [
            _cond("dob", "exists", True),
            _cond("dob", "exists", True),  # duplicate request for same field
            _cond("gender", "exists", True),
        ]
    }
    outcome = evaluate(_rules(tree), {})
    assert list(outcome.missing_fields) == ["dob", "gender"]


def test_multiple_missing_fields_listed() -> None:
    tree = {
        "all": [
            _cond("annual_income", "exists", True),
            _cond("state", "exists", True),
            _cond("pincode", "exists", True),
        ]
    }
    outcome = evaluate(_rules(tree), {"state": "Tamil Nadu"})
    assert outcome.status == NEEDS_INFO
    assert list(outcome.missing_fields) == ["annual_income", "pincode"]


def test_reasons_report_only_leaf_conditions() -> None:
    tree = {"all": [_cond("age", ">=", 18), _cond("occupation", "==", "farmer")]}
    outcome = evaluate(_rules(tree), {"age": 30, "occupation": "weaver"})
    assert len(outcome.reasons) == 2
    assert [reason.ok for reason in outcome.reasons] == [True, False]


def test_eligible_has_at_least_one_ok_reason_per_group() -> None:
    tree = {
        "all": [
            _cond("age", ">=", 18),
            {"any": [_cond("is_student", "==", True), _cond("occupation", "==", "farmer")]},
        ]
    }
    outcome = evaluate(_rules(tree), {"age": 30, "is_student": False, "occupation": "farmer"})
    assert outcome.status == ELIGIBLE
    ok_fields = {reason.field for reason in outcome.reasons if reason.ok}
    assert {"age", "occupation"} <= ok_fields
