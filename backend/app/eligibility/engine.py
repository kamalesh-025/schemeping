"""The eligibility evaluation engine (Phase 3 brain).

Given one validated rule tree and one context dict (a person, a household, or
an event window), this module computes one of exactly three outcomes:

- ``eligible``      every required condition is satisfied
- ``not_eligible``  at least one required condition is definitely not satisfied
- ``needs_info``    no condition failed, but some fields are missing

It uses **three-valued logic**: every leaf condition is ``True``, ``False``,
or ``None`` (unknown, because the field is missing from the context). Groups
combine the leaves without ever guessing.

This module is pure: no database access, no network calls, no AI output. The
same input always yields the same output, so results are auditable.

Reasons are simple structured dicts (AGENTS.md §8.2)::

    {"field": "annual_income", "ok": true, "user_value": 180000,
     "required": "<= 250000"}

``ok`` is ``False`` for leaves inside a ``not`` group that the citizen
satisfies, because inversion is expressed in the ``required`` string; the UI
shows the ``required`` text either way.

A value whose type cannot be compared with the rule (for example a string
income against a numeric bound) counts as a failing condition, not as an
unknown: the field exists, it just cannot satisfy the rule.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from app.eligibility.rules import validate_eligibility_rules

ELIGIBLE = "eligible"
NOT_ELIGIBLE = "not_eligible"
NEEDS_INFO = "needs_info"

# Result of one leaf or one subtree: True, False, or None (unknown).
Third = bool | None

_ELIGIBLE_RANK = {ELIGIBLE: 2, NEEDS_INFO: 1, NOT_ELIGIBLE: 0}


def is_better(a: str, b: str) -> bool:
    """True when outcome ``a`` is more informative for the user than ``b``.

    The first ``eligible`` outcome wins, and ``needs_info`` beats
    ``not_eligible`` (an unknown answer is closer to a yes than a no).
    """
    return _ELIGIBLE_RANK[a] > _ELIGIBLE_RANK[b]


@dataclass(frozen=True)
class Reason:
    """One auditable fact about a condition."""

    field: str
    ok: bool
    user_value: Any | None
    required: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "ok": self.ok,
            "user_value": self.user_value,
            "required": self.required,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Reason:
        return cls(
            field=str(payload.get("field")),
            ok=bool(payload.get("ok")),
            user_value=payload.get("user_value"),
            required=str(payload.get("required")),
        )


@dataclass(frozen=True)
class EligibilityOutcome:
    """The result of evaluating one rule tree against one context."""

    status: str
    reasons: tuple[Reason, ...]
    missing_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reasons": [reason.as_dict() for reason in self.reasons],
            "missing_fields": list(self.missing_fields),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EligibilityOutcome:
        return cls(
            status=str(payload.get("status")),
            reasons=tuple(Reason.from_dict(item) for item in payload.get("reasons", [])),
            missing_fields=tuple(payload.get("missing_fields", [])),
        )

    @classmethod
    def from_restored(
        cls,
        status: str,
        reasons: list[dict[str, Any]] | None,
        missing_fields: list[str] | None,
    ) -> EligibilityOutcome:
        """Rebuild an outcome from the shape stored in ``eligibility_results``."""
        return cls(
            status=status,
            reasons=tuple(Reason.from_dict(item) for item in (reasons or [])),
            missing_fields=tuple(missing_fields or []),
        )


def _present(value: Any) -> bool:
    """A field counts as present when it is neither absent, ``None``, nor empty."""
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def _scalar_text(value: Any) -> str:
    """Human-ish text for a value inside a ``required`` string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "[" + ", ".join(_scalar_text(item) for item in value) + "]"
    return str(value)


def _required_string(node: Mapping[str, Any]) -> str:
    field_name = str(node["field"])
    op = str(node["op"])
    value = cast(Any, node.get("value"))

    if op == "between":
        low, high = value
        return f"{field_name} between {_scalar_text(low)} and {_scalar_text(high)}"
    if op == "exists":
        return f"{field_name} exists"
    return f"{field_name} {op} {_scalar_text(value)}"


def _compare(actual: Any, op: str, rule_value: Any) -> Third:
    """Apply one ordered comparison; incomparable types fail, never guess."""
    result: bool
    try:
        if op == "<":
            result = actual < rule_value
        elif op == "<=":
            result = actual <= rule_value
        elif op == ">":
            result = actual > rule_value
        else:
            result = actual >= rule_value
    except TypeError:
        return False
    return result


def _eval_condition(node: Mapping[str, Any], context: Mapping[str, Any]) -> Third:
    field_name = str(node["field"])
    op = str(node["op"])
    rule_value = cast(Any, node.get("value"))
    actual = context.get(field_name)

    if op == "exists":
        # A missing context key really is unknown: we cannot say the field
        # exists. A present (non-empty) value gives a definite answer.
        if not _present(actual):
            return None
        return rule_value is True

    if not _present(actual):
        return None

    if op == "==" or op == "!=" or op == "in" or op == "not_in":
        outcome: bool
        if op == "==":
            outcome = actual == rule_value
        elif op == "!=":
            outcome = actual != rule_value
        elif op == "in":
            outcome = actual in rule_value
        else:
            outcome = actual not in rule_value
        return outcome
    if op == "between":
        low, high = rule_value
        return _compare(actual, ">=", low) and _compare(actual, "<=", high)
    return _compare(actual, op, rule_value)


def _combine_all(thirds: list[Third]) -> Third:
    if False in thirds:
        return False
    if None in thirds:
        return None
    return True


def _combine_any(thirds: list[Third]) -> Third:
    if True in thirds:
        return True
    if None in thirds:
        return None
    return False


def _eval_node(
    node: Mapping[str, Any], context: Mapping[str, Any]
) -> tuple[Third, list[Reason], list[str]]:
    """Evaluate one subtree: a three-value verdict plus reasons and gaps."""
    for group_key in ("all", "any"):
        if group_key in node:
            thirds: list[Third] = []
            reasons: list[Reason] = []
            missing: list[str] = []
            for child in node[group_key]:
                child_third, child_reasons, child_missing = _eval_node(child, context)
                thirds.append(child_third)
                reasons.extend(child_reasons)
                missing.extend(child_missing)
            if group_key == "all":
                return _combine_all(thirds), reasons, missing
            return _combine_any(thirds), reasons, missing

    if "not" in node:
        third, reasons, missing = _eval_node(node["not"], context)
        if third is None:
            return None, reasons, missing
        inverted: list[Reason] = [
            Reason(
                field=reason.field,
                ok=not reason.ok,
                user_value=reason.user_value,
                required=f"not ({reason.required})",
            )
            for reason in reasons
        ]
        return (not third), inverted, missing

    field_name = str(node["field"])
    third = _eval_condition(node, context)
    reason = Reason(
        field=field_name,
        ok=bool(third) if third is not None else False,
        user_value=context.get(field_name),
        required=_required_string(node),
    )
    missing_fields = [field_name] if third is None else []
    return third, [reason], missing_fields


def evaluate(rules: Mapping[str, Any], context: Mapping[str, Any]) -> EligibilityOutcome:
    """Evaluate one rule tree against one context.

    ``rules`` is the ``eligibility_rules`` JSON (``applies_to`` plus the rule
    tree). It is re-validated defensively so a corrupted database row can never
    make the engine crash or silently guess.

    Returns an ``EligibilityOutcome`` whose ``status`` is one of
    ``eligible`` / ``not_eligible`` / ``needs_info``. Unknown leaves are
    collected into ``missing_fields`` in first-seen rule order, de-duplicated.
    """
    validated = validate_eligibility_rules(dict(rules))
    tree = validated["rules"]

    third, reasons, missing = _eval_node(tree, context)

    status: str
    if third is True:
        status = ELIGIBLE
    elif third is False:
        status = NOT_ELIGIBLE
    else:
        status = NEEDS_INFO

    seen_missing: set[str] = set()
    deduped_missing: list[str] = []
    for field_name in missing:
        if field_name not in seen_missing:
            seen_missing.add(field_name)
            deduped_missing.append(field_name)

    return EligibilityOutcome(
        status=status,
        reasons=tuple(reasons),
        missing_fields=tuple(deduped_missing),
    )
