"""Family member CRUD and per-user isolation."""

from __future__ import annotations

MEMBER = {
    "name": "Karthik Narayanan",
    "relationship": "son",
    "dob": "2012-03-04",
    "gender": "male",
    "occupation": None,
    "education_status": "secondary",
    "annual_income": 0,
    "is_disabled": False,
    "is_student": True,
    "is_widow": False,
}


def test_family_routes_require_authentication(client) -> None:
    assert client.get("/api/v1/family").status_code == 401
    assert client.post("/api/v1/family", json=MEMBER).status_code == 401


def test_create_list_read_and_delete(logged_in_client) -> None:
    created = logged_in_client.post("/api/v1/family", json=MEMBER)
    assert created.status_code == 201, created.text
    member = created.json()
    assert member["relationship"] == "son"
    assert member["age"] is not None
    assert member["is_minor"] is True
    assert member["is_senior"] is False

    listed = logged_in_client.get("/api/v1/family").json()
    assert [m["id"] for m in listed] == [member["id"]]

    fetched = logged_in_client.get(f"/api/v1/family/{member['id']}")
    assert fetched.status_code == 200

    assert logged_in_client.delete(f"/api/v1/family/{member['id']}").status_code == 204
    assert logged_in_client.get("/api/v1/family").json() == []


def test_senior_flag_is_derived_from_dob(logged_in_client) -> None:
    created = logged_in_client.post(
        "/api/v1/family",
        json={**MEMBER, "name": "Grandmother", "relationship": "mother", "dob": "1950-01-01"},
    )
    body = created.json()
    assert body["is_senior"] is True
    assert body["is_minor"] is False


def test_relationship_self_is_rejected(logged_in_client) -> None:
    response = logged_in_client.post(
        "/api/v1/family", json={**MEMBER, "relationship": "self"}
    )
    assert response.status_code == 422


def test_partial_update_changes_only_given_fields(logged_in_client) -> None:
    member = logged_in_client.post("/api/v1/family", json=MEMBER).json()

    response = logged_in_client.patch(
        f"/api/v1/family/{member['id']}", json={"annual_income": 50000}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["annual_income"] == 50000
    assert updated["name"] == MEMBER["name"]
    assert updated["relationship"] == "son"


def test_updating_dob_recomputes_senior_flag(logged_in_client) -> None:
    member = logged_in_client.post("/api/v1/family", json=MEMBER).json()
    assert member["is_senior"] is False

    response = logged_in_client.patch(
        f"/api/v1/family/{member['id']}", json={"dob": "1948-05-05"}
    )
    assert response.json()["is_senior"] is True
    assert response.json()["is_minor"] is False


def test_is_senior_column_is_persisted(logged_in_client, db) -> None:
    from app.models.family import FamilyMember

    logged_in_client.post(
        "/api/v1/family",
        json={**MEMBER, "name": "Elder", "relationship": "father", "dob": "1945-02-02"},
    )
    member = db.query(FamilyMember).one()
    assert member.is_senior is True


def test_user_cannot_read_another_users_family(
    logged_in_client, make_logged_in_client
) -> None:
    mine = logged_in_client.post("/api/v1/family", json=MEMBER).json()

    other = make_logged_in_client("9123456780")
    assert other.get(f"/api/v1/family/{mine['id']}").status_code == 404
    assert other.get("/api/v1/family").json() == []


def test_user_cannot_modify_or_delete_another_users_family(
    logged_in_client, make_logged_in_client
) -> None:
    mine = logged_in_client.post("/api/v1/family", json=MEMBER).json()
    other = make_logged_in_client("9123456780")

    assert (
        other.patch(
            f"/api/v1/family/{mine['id']}", json={"name": "Hacked"}
        ).status_code
        == 404
    )
    assert other.delete(f"/api/v1/family/{mine['id']}").status_code == 404

    # The original member is untouched.
    assert logged_in_client.get(f"/api/v1/family/{mine['id']}").status_code == 200


def test_family_member_count_is_capped(logged_in_client, monkeypatch) -> None:
    import app.api.family as family_module

    monkeypatch.setattr(family_module, "MAX_FAMILY_MEMBERS", 1)

    assert logged_in_client.post("/api/v1/family", json=MEMBER).status_code == 201
    second = logged_in_client.post(
        "/api/v1/family", json={**MEMBER, "name": "Second Child"}
    )
    assert second.status_code == 409
