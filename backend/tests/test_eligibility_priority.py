"""The documented priority rule, as a small isolated function."""

from __future__ import annotations

import pytest
from app.eligibility.priority import HIGH, MEDIUM, NORMAL, priority_level


@pytest.mark.parametrize(
    ("days_remaining", "benefit_amount", "expected"),
    [
        # Deadline within 14 days: high regardless of the amount.
        (0, None, HIGH),  # deadline today
        (14, None, HIGH),  # boundary: exactly 14
        (3, "INR 2000", HIGH),
        # Deadline within 30 days: medium.
        (15, None, MEDIUM),  # boundary: one past high
        (30, None, MEDIUM),  # boundary: exactly 30
        # Large benefits: medium.
        (None, "Up to INR 10,000", MEDIUM),
        (None, "INR 350000", MEDIUM),
        (45, "₹15,000 a year", MEDIUM),
        # Everything else: normal.
        (None, None, NORMAL),
        (31, None, NORMAL),
        (None, "INR 500", NORMAL),
        (None, "One bicycle", NORMAL),
        (200, "Up to INR 9000", NORMAL),  # small amount, far deadline
        (-5, None, NORMAL),  # deadline passed
        (None, "Free coaching classes", NORMAL),
    ],
)
def test_priority_table(
    days_remaining: int | None, benefit_amount: str | None, expected: str
) -> None:
    assert (
        priority_level(days_remaining=days_remaining, benefit_amount=benefit_amount)
        == expected
    )


def test_large_amount_bounded_parse() -> None:
    # "Up to INR 500000 per year" mentions no tiny fragment before the amount.
    assert (
        priority_level(
            days_remaining=None,
            benefit_amount="Up to INR 500000 per year",
        )
        == MEDIUM
    )
