"""Phase 3: the account owner may declare a disability.

Phase 3 rule fields include ``is_disabled`` (individual) and
``has_disabled_member`` (household). Family members already carry a
disability flag; the head of household needs one too, or every disability
scheme would stay ``needs_info`` for the account owner and household
aggregation would be permanently unknown.

Revision ID: 7c9e2f4a8b01
Revises: a1b2c3d4e5f6
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c9e2f4a8b01"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Disabled status of the account owner is sensitive (DPDP): same
    # EncryptedString storage the family member flag uses.
    op.add_column("users", sa.Column("is_disabled", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "is_disabled")
