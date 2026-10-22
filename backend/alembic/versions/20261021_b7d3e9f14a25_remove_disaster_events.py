"""Phase 6 follow-up: remove the disaster broadcast feature.

SchemePing is now fully scheme-based: there are no admin-authored disaster
events, no disaster broadcasts, and no ``scope=event`` schemes. This
migration drops the ``disaster_events`` table (the enum column is stored as
VARCHAR, so no enum type has to be dropped).

Revision ID: b7d3e9f14a25
Revises: e4f8a2c6d907
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b7d3e9f14a25"
down_revision: str | None = "e4f8a2c6d907"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("disaster_events")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "disaster_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "flood",
                "cyclone",
                "drought",
                "earthquake",
                "landslide",
                "other",
                name="disastertype",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=250), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("helpline_numbers", sa.JSON(), nullable=False),
        sa.Column("relief_scheme_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=150), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["relief_scheme_id"],
            ["schemes.id"],
            name=op.f("fk_disaster_events_relief_scheme_id_schemes"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
