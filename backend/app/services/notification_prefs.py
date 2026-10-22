"""Per-category notification preferences.

A leaf module (no application imports) so models, services, and the API can
all share it without import cycles. A category that is absent from a stored
JSON blob (older rows) counts as enabled — new categories default to on.
"""

from __future__ import annotations

from typing import Any

# The four proactive categories a user can toggle. The user-initiated
# "Send to WhatsApp" (scheme_summary) is NOT in this list: it is only
# governed by the WhatsApp opt-in itself.
CATEGORIES: tuple[str, ...] = (
    "new_schemes",
    "family_milestones",
    "deadlines",
    "festival",
)


def default_notification_prefs() -> dict[str, Any]:
    """All categories on by default; opt-in to WhatsApp remains explicit."""
    return dict.fromkeys(CATEGORIES, True)


def merge_notification_prefs(raw: object) -> dict[str, bool]:
    """Normalise any stored blob into a full {category: bool} mapping."""
    merged = default_notification_prefs()
    if isinstance(raw, dict):
        for category in CATEGORIES:
            value = raw.get(category)
            if isinstance(value, bool):
                merged[category] = value
    return merged


def category_enabled(raw: object, category: str) -> bool:
    return merge_notification_prefs(raw).get(category, True)
