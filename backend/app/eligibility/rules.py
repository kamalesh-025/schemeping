"""Structural validation for eligibility rule JSON.

This module deliberately implements **only** structural validation: it answers
"is this a well-formed rule tree?" It does not evaluate eligibility (that is the
Phase 3 engine) and it never consults the database. The seed pipeline uses it so
that malformed rules can never reach the ``schemes`` table.

Rule grammar
------------
::

    RuleGroup  := {"all": [Node, ...]} | {"any": [Node, ...]} | {"not": Node}
    Node       := RuleGroup | Condition
    Condition  := {"field": str, "op": <operator>, "value": <json>}

Operators and their value requirements:

===========  ==================================================
``== != < <= > >=``  exactly one JSON value
``in not_in``        a non-empty list
``between``          a list of exactly two comparable values
``exists``           a boolean
===========  ==================================================
"""

from __future__ import annotations

from typing import Any, cast

SUPPORTED_OPERATORS = frozenset(
    {"==", "!=", "<", "<=", ">", ">=", "in", "not_in", "between", "exists"}
)
GROUP_KEYS = frozenset({"all", "any", "not"})
APPLIES_TO = frozenset({"individual", "family"})

# Fields the engine knows how to read. Unknown fields are rejected at load time
# so a typo can never silently make every citizen ineligible.
KNOWN_FIELDS = frozenset(
    {
        # individual
        "age",
        "dob",
        "gender",
        "annual_income",
        "occupation",
        "education",
        "education_status",
        "marital_status",
        "relationship",
        "state",
        "district",
        "pincode",
        "is_student",
        "is_widow",
        "is_disabled",
        "is_senior",
        # household
        "household_income",
        "family_size",
        "has_senior",
        "has_girl_child",
        "has_disabled_member",
        "has_student",
    }
)


class RuleValidationError(ValueError):
    """Raised when an eligibility rule tree is malformed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuleValidationError(message)


def _validate_condition(node: dict[str, Any], path: str) -> None:
    _require(isinstance(node.get("field"), str) and node["field"], f"{path}: missing 'field'")
    field = node["field"]
    _require(field in KNOWN_FIELDS, f"{path}: unknown field {field!r}")

    op = node.get("op")
    _require(isinstance(op, str), f"{path}: missing 'op'")
    _require(op in SUPPORTED_OPERATORS, f"{path}: unsupported operator {op!r}")
    _require("value" in node, f"{path}: missing 'value'")
    value = node["value"]

    if op in {"in", "not_in"}:
        _require(bool(isinstance(value, list) and value), f"{path}: '{op}' needs a non-empty list")
    elif op == "between":
        _require(
            isinstance(value, list) and len(value) == 2,
            f"{path}: 'between' needs [low, high]",
        )
        low, high = value
        _require(
            isinstance(low, (int | float)) and isinstance(high, (int | float)),
            f"{path}: 'between' bounds must be numbers",
        )
        _require(low <= high, f"{path}: 'between' bounds are reversed")
    elif op == "exists":
        _require(isinstance(value, bool), f"{path}: 'exists' needs a boolean")
    else:
        _require(
            not isinstance(value, (dict | list)),
            f"{path}: operator {op!r} needs a scalar value",
        )


def _validate_node(node: Any, path: str, depth: int) -> None:
    _require(depth <= 12, f"{path}: rule nesting is too deep (max 12)")
    _require(isinstance(node, dict), f"{path}: node must be an object")

    group_keys = GROUP_KEYS.intersection(node)
    if group_keys:
        _require(len(group_keys) == 1, f"{path}: a group may use only one of all/any/not")
        _require(
            "field" not in node and "op" not in node,
            f"{path}: a group cannot also be a condition",
        )
        key = next(iter(group_keys))
        children = node[key]

        if key == "not":
            _validate_node(children, f"{path}.not", depth + 1)
            return

        _require(isinstance(children, list), f"{path}.{key}: must be a list")
        _require(children, f"{path}.{key}: must not be empty")
        for index, child in enumerate(children):
            _validate_node(child, f"{path}.{key}[{index}]", depth + 1)
        return

    _validate_condition(node, path)


def validate_eligibility_rules(rules: Any) -> dict[str, Any]:
    """Validate and return ``rules`` unchanged, or raise ``RuleValidationError``.

    Expected shape::

        {"applies_to": "individual", "rules": {"all": [...]}}
    """
    _require(isinstance(rules, dict), "eligibility_rules must be an object")

    applies_to = rules.get("applies_to")
    _require(isinstance(applies_to, str), "eligibility_rules.applies_to is required")
    _require(
        applies_to in APPLIES_TO,
        f"applies_to must be one of {sorted(APPLIES_TO)}, got {applies_to!r}",
    )

    tree = rules.get("rules")
    _require(isinstance(tree, dict), "eligibility_rules.rules must be an object")
    _validate_node(tree, "rules", depth=0)

    return cast(dict[str, Any], rules)


def iter_conditions(node: Any) -> list[dict[str, Any]]:
    """Flatten a validated rule tree into its conditions (used by tests/tools)."""
    conditions: list[dict[str, Any]] = []
    if not isinstance(node, dict):
        return conditions
    for key in ("all", "any"):
        if key in node:
            for child in node[key]:
                conditions.extend(iter_conditions(child))
    if "not" in node:
        conditions.extend(iter_conditions(node["not"]))
    if "field" in node:
        conditions.append(node)
    return conditions
