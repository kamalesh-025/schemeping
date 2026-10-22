"""Archive legacy event-scoped schemes.

Event schemes are no longer supported. Older databases may still contain
published rows with ``scope='event'``, which the current SchemeScope enum
cannot deserialize. Preserve those records as archived and normalize their
scope so they remain readable.

Revision ID: c8f0a2d9e614
Revises: b7d3e9f14a25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "c8f0a2d9e614"
down_revision: str | None = "b7d3e9f14a25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE schemes "
        "SET status = 'archived', scope = 'individual' "
        "WHERE scope = 'event'"
    )


def downgrade() -> None:
    # The removed event scope cannot be restored without risking reactivating
    # records that were independently archived after this migration.
    pass
