"""Account deletion removes the user and every related row."""

from __future__ import annotations

from app.models.family import FamilyMember
from app.models.refresh_token import RefreshToken
from app.models.user import User
from sqlalchemy import select

MEMBER = {
    "name": "Karthik Narayanan",
    "relationship": "son",
    "dob": "2012-03-04",
    "gender": "male",
    "is_student": True,
}


def test_delete_account_erases_user_and_family(logged_in_client, db) -> None:
    member = logged_in_client.post("/api/v1/family", json=MEMBER).json()
    assert member["id"]

    response = logged_in_client.request(
        "DELETE", "/api/v1/me", json={"confirm": "DELETE"}
    )
    assert response.status_code == 204

    db.rollback()
    assert db.query(User).count() == 0
    assert db.query(FamilyMember).count() == 0
    assert db.query(RefreshToken).count() == 0


def test_delete_account_erases_chat_and_keeps_analytics_anonymous(
    logged_in_client, db
) -> None:
    """Phase 6: chat history goes, analytics rows lose the personal link."""
    from app.models.analytics import AnalyticsEvent
    from app.models.chat import ChatMessage
    from app.models.enums import ChatRole
    from app.models.user import User

    user = db.scalars(select(User)).first()
    assert user is not None
    db.add(
        ChatMessage(user_id=user.id, role=ChatRole.USER, content="my question")
    )
    db.add(AnalyticsEvent(user_id=user.id, kind="scheme_view"))
    db.commit()

    response = logged_in_client.request(
        "DELETE", "/api/v1/me", json={"confirm": "DELETE"}
    )
    assert response.status_code == 204

    db.rollback()
    assert db.query(ChatMessage).count() == 0
    events = db.scalars(select(AnalyticsEvent)).all()
    # The row survives for aggregate reporting, but the person is gone.
    assert all(event.user_id is None for event in events)


def test_session_is_dead_after_account_deletion(logged_in_client) -> None:
    assert (
        logged_in_client.request("DELETE", "/api/v1/me", json={"confirm": "DELETE"}).status_code
        == 204
    )
    # Cookies were cleared, and the user row no longer exists.
    assert logged_in_client.get("/api/v1/me").status_code == 401


def test_delete_does_not_touch_other_users(
    logged_in_client, make_logged_in_client, db
) -> None:
    other = make_logged_in_client("9123456780")
    other.post("/api/v1/family", json={**MEMBER, "name": "Other Child"})

    logged_in_client.request("DELETE", "/api/v1/me", json={"confirm": "DELETE"})

    db.rollback()
    remaining = db.scalars(select(User)).all()
    assert len(remaining) == 1
    assert remaining[0].mobile == "9123456780"
    assert db.query(FamilyMember).count() == 1
