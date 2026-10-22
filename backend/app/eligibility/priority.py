"""Card priority levels for the dashboard.

Phase 3 requirement: a simple, documented rule implemented as one small
isolated function, so the accident of scheme creation order never dictates
what a citizen sees first.

Documented rule (English, mirrored in the README):

- ``high``    the deadline is within 14 days; else
- ``medium``  the deadline is within 30 days, or the benefit mentions an
              amount of ₹10,000 or more; else
- ``normal``  everything else.

``benefit_amount`` is free text on the scheme record ("Up to ₹15,000 a
month"), so the value is extracted from the first monetary amount found in
the text. A scheme with no parseable amount falls through on that test.

Pure module: no database, no network.
"""

from __future__ import annotations

import re

HIGH = "high"
MEDIUM = "medium"
NORMAL = "normal"

_BIG_BENEFIT_AMOUNT = 10_000
_URGENT_DAYS = 14
_SOON_DAYS = 30

# Matches the first number in a benefit string: handles "15000", "₹15,000"
# and "INR 10000". Leading groups smaller than 3 digits ("2 in ₹2,000") are
# skipped so fragments like "BPL" or "AAY" lists cannot shadow the amount.
_NUMBER_RE = re.compile(r"\d{3,5}")


def _first_amount(benefit_amount: str | None) -> int | None:
    if not benefit_amount:
        return None
    compact = benefit_amount.replace(",", "")
    for match in _NUMBER_RE.finditer(compact):
        amount = int(match.group())
        if amount >= 500:
            return amount
    return None


def priority_level(
    *,
    days_remaining: int | None,
    benefit_amount: str | None = None,
) -> str:
    """Return ``high``, ``medium``, or ``normal`` for one scheme card."""
    if days_remaining is not None and 0 <= days_remaining <= _URGENT_DAYS:
        return HIGH

    big_benefit = (_first_amount(benefit_amount) or 0) >= _BIG_BENEFIT_AMOUNT
    if big_benefit:
        return MEDIUM

    if days_remaining is not None and 0 <= days_remaining <= _SOON_DAYS:
        return MEDIUM

    return NORMAL
