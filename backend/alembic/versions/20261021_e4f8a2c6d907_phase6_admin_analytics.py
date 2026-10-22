"""Phase 6: admin accounts, analytics events and Metabase SQL views.

- ``admin_users``: staff accounts with PBKDF2 hashes and TOTP seeds.
- ``analytics_events``: lightweight scheme-view/apply-click tracking.
- MySQL views for Metabase: geo users, eligible matches, notification
  stats and scheme events.

Revision ID: e4f8a2c6d907
Revises: c3d7e2a91b54
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f8a2c6d907"
down_revision: str | None = "c3d7e2a91b54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEWS: tuple[str, ...] = (
    """
    CREATE OR REPLACE VIEW v_users_by_geo AS
    SELECT state, district, COUNT(*) AS users
    FROM users
    WHERE deleted_at IS NULL
    GROUP BY state, district
    """,
    """
    CREATE OR REPLACE VIEW v_family_counts AS
    SELECT u.state, u.district,
           COUNT(DISTINCT u.id) AS users,
           COUNT(f.id) AS family_members
    FROM users u
    LEFT JOIN family_members f ON f.user_id = u.id
    WHERE u.deleted_at IS NULL
    GROUP BY u.state, u.district
    """,
    """
    CREATE OR REPLACE VIEW v_eligible_matches AS
    SELECT s.id AS scheme_id, s.name, s.status AS scheme_status,
           er.status AS result_status, COUNT(*) AS people
    FROM eligibility_results er
    JOIN schemes s ON s.id = er.scheme_id
    GROUP BY s.id, s.name, s.status, er.status
    """,
    """
    CREATE OR REPLACE VIEW v_notification_stats AS
    SELECT template_name, status, COUNT(*) AS messages
    FROM notifications
    GROUP BY template_name, status
    """,
    """
    CREATE OR REPLACE VIEW v_scheme_events AS
    SELECT scheme_id, kind,
           DATE(created_at) AS event_date,
           COUNT(*) AS hits
    FROM analytics_events
    GROUP BY scheme_id, kind, DATE(created_at)
    """,
)


def upgrade() -> None:
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("totp_secret", sa.String(256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "analytics_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column(
            "scheme_id", sa.Integer(), sa.ForeignKey("schemes.id", ondelete="SET NULL")
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_analytics_events_kind_created", "analytics_events", ["kind", "created_at"]
    )
    op.create_index("ix_analytics_events_scheme", "analytics_events", ["scheme_id"])
    op.create_index("ix_analytics_events_user", "analytics_events", ["user_id"])

    for view in _VIEWS:
        op.execute(view)


def downgrade() -> None:
    for view in _VIEWS:
        name = view.replace("\n", " ").split("VIEW", 1)[1].split(" AS", 1)[0].strip()
        op.execute(f"DROP VIEW IF EXISTS {name}")
    op.drop_index("ix_analytics_events_user", table_name="analytics_events")
    op.drop_index("ix_analytics_events_scheme", table_name="analytics_events")
    op.drop_index(
        "ix_analytics_events_kind_created", table_name="analytics_events"
    )
    op.drop_table("analytics_events")
    op.drop_table("admin_users")
