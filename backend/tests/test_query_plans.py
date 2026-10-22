"""The main queries must use their indexes (Part D, performance review).

Each test runs EXPLAIN on a hot query and asserts the plan uses an index
rather than a full table scan on the joined tables. The dataset is tiny, so
the assertion is about the plan shape, not the row counts.
"""

from __future__ import annotations

from sqlalchemy import text

from tests.conftest import make_completed_profile
from tests.test_translation_service import make_scheme


def _plan(db, query: str, params: dict | None = None) -> str:
    result = db.execute(text(f"EXPLAIN {query}"), params or {})
    return " ".join(str(value) for row in result.fetchall() for value in row)


def test_eligibility_cards_use_an_index(db):
    make_completed_profile(db)
    make_scheme(db)
    plan = _plan(
        db,
        """
        SELECT er.id FROM eligibility_results er
        WHERE er.user_id = 1 AND er.status = 'eligible'
        """,
    )
    assert "ix_eligibility" in plan.lower() or "key" in plan.lower()


def test_user_lookup_by_mobile_uses_the_unique_index(db):
    make_completed_profile(db)
    plan = _plan(db, "SELECT id FROM users WHERE mobile = '9876543210'")
    assert "ix_users_mobile" in plan


def test_scheme_list_by_status_uses_the_status_index(db):
    make_scheme(db)
    plan = _plan(db, "SELECT id FROM schemes WHERE status = 'published'")
    assert "ix_schemes" in plan or "PRIMARY" in plan


def test_notification_dedupe_lookup_uses_the_unique_index(db):
    from app.models.enums import NotificationStatus, NotificationType
    from app.models.notification import Notification

    user = make_completed_profile(db)
    db.add(
        Notification(
            user_id=user.id,
            type=NotificationType.SCHEME_SUMMARY,
            template_name="scheme_summary",
            payload={},
            status=NotificationStatus.QUEUED,
            dedupe_key="abc",
        )
    )
    db.commit()
    plan = _plan(
        db,
        "SELECT id FROM notifications WHERE dedupe_key = 'abc' LIMIT 1",
    )
    assert "ix_notifications_dedupe_key" in plan or "dedupe" in plan.lower()


def test_geo_lookup_uses_the_state_district_index(db):
    make_completed_profile(db)
    plan = _plan(
        db,
        "SELECT id FROM users WHERE state = 'Tamil Nadu' AND district = 'Erode'",
    )
    assert "ix_users_state_district" in plan


def test_chat_history_lookup_uses_the_user_created_index(db):
    plan = _plan(
        db,
        "SELECT id FROM chat_messages WHERE user_id = 1 ORDER BY created_at DESC",
    )
    assert "ix_chat_messages_user_created" in plan


def test_analytics_events_kind_index_exists(db):
    plan = _plan(
        db,
        "SELECT COUNT(*) FROM analytics_events WHERE kind = 'scheme_view'",
    )
    assert "ix_analytics_events_kind_created" in plan
