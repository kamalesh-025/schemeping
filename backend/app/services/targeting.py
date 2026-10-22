"""Region matching for scheme broadcasts.

The festival broadcast tells opted-in users about a scheme that only applies
to their state. This module owns that one question: does the scheme's
region list cover this person? Admin-authored region JSON may be a dict
(``{"state": "Tamil Nadu"}`` / ``{"district": "Erode"}``) or a plain string,
so the matcher accepts both.
"""

from __future__ import annotations

from typing import Any


def region_covers(
    regions: list[Any], state: str | None, district: str | None
) -> bool:
    """Whether the region list covers the given address."""
    for entry in regions or []:
        if isinstance(entry, dict):
            target_state = entry.get("state")
            target_district = entry.get("district")
            if target_state and str(target_state) == state:
                return True
            if target_district and str(target_district) == district:
                return True
        elif entry in (district, state):
            return True
    return False
