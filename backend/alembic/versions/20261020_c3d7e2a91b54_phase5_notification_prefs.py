"""Phase 5: per-category notification preferences.

Adds ``users.notification_prefs`` (JSON). The defaults (all categories on)
are filled by the ORM for new rows; existing rows receive the standard all-on
blob because a missing key counts as enabled anyway.

Revision ID: c3d7e2a91b54
Revises: 7c9e2f4a8b01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d7e2a91b54"
down_revision: str | None = "7c9e2f4a8b01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # MySQL does not support plain JSON column defaults; NULL is treated as
    # "all categories on" by notification_prefs.merge_notification_prefs and
    # new ORM rows are filled by a Python-side default.
    op.add_column("users", sa.Column("notification_prefs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "notification_prefs")
