"""The Metabase SQL views must exist and return data (Part C acceptance)."""

from __future__ import annotations

from sqlalchemy import text

from tests.conftest import make_completed_profile
from tests.test_translation_service import make_scheme


def _rows(db, view: str) -> list[dict]:
    result = db.execute(text(f"SELECT * FROM {view}"))
    keys = list(result.keys())
    return [dict(zip(keys, row, strict=False)) for row in result.fetchall()]


def test_all_documented_views_exist(db):
    expected = {
        "v_users_by_geo",
        "v_family_counts",
        "v_eligible_matches",
        "v_notification_stats",
        "v_scheme_events",
    }
    existing = {
        row[0]
        for row in db.execute(
            text(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = DATABASE()"
            )
        ).fetchall()
    }
    assert expected <= existing, sorted(expected - existing)


def test_users_by_geo_view_returns_rows(db):
    make_completed_profile(db)
    rows = _rows(db, "v_users_by_geo")
    assert rows
    assert rows[0]["state"]
    assert rows[0]["users"] >= 1


def test_family_counts_view(db):
    make_completed_profile(db)
    rows = _rows(db, "v_family_counts")
    assert rows
    assert "family_members" in rows[0]


def test_eligible_matches_view(db):
    from app.services.eligibility import recompute_user

    user = make_completed_profile(db)
    scheme = make_scheme(
        db,
        slug="eligible-one",
        eligibility_rules={
            "applies_to": "individual",
            "rules": {"all": [{"field": "state", "op": "==", "value": "Tamil Nadu"}]},
        },
    )
    recompute_user(db, user)
    rows = _rows(db, "v_eligible_matches")
    assert any(row["scheme_id"] == scheme.id for row in rows)
    assert all("result_status" in row for row in rows)


def test_notification_stats_view(db):
    from app.models.enums import NotificationStatus, NotificationType
    from app.models.notification import Notification

    user = make_completed_profile(db)
    db.add(
        Notification(
            user_id=user.id,
            type=NotificationType.SCHEME_SUMMARY,
            template_name="scheme_summary",
            payload={},
            status=NotificationStatus.SENT,
        )
    )
    db.commit()
    rows = _rows(db, "v_notification_stats")
    assert any(row["template_name"] == "scheme_summary" for row in rows)


def test_scheme_events_view(db):
    from app.models.analytics import AnalyticsEvent

    user = make_completed_profile(db)
    db.add(AnalyticsEvent(user_id=user.id, kind="scheme_view"))
    db.commit()
    rows = _rows(db, "v_scheme_events")
    assert any(row["kind"] == "scheme_view" for row in rows)
