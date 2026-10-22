"""Add users.password_hash for password sign-in.

Revision ID: f2a7c4d81b60
Revises: c8f0a2d9e614

Nullable on purpose: accounts created by an OTP flow have no password. They can
still sign in with ``AUTH_MODE=otp``, and an operator sets a password with
``python -m app.scripts.reset_password <mobile>`` before password mode is used.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a7c4d81b60"
down_revision: str | None = "c8f0a2d9e614"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "password_hash")
