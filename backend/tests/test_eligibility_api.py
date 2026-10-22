"""Eligibility API and service integration tests.

Seed sample schemes are published in the test database, a household is built
through the real profile/family endpoints, and the dashboard cards are read
through ``GET /eligibility``. Expected outcomes are derived from the pure
engine rule set, never hard-coded per running date.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models.enums import SchemeStatus
from app.models.scheme import Scheme

PROFILE = {
    "name": "Malar Selvam",
    "dob": "1981-02-02",  # adult, not senior
    "gender": "male",
    "occupation": "farmer",
    "annual_income": 150000,
    "education": None,
    "marital_status": "married",
    "state": "Tamil Nadu",
    "district": "Coimbatore",
    "locality": None,
    "pincode": "641001",
    "language": "ta",
    "data_processing_consent": True,
}

# A 10-year-old daughter on every possible run date.
DAUGHTER = {
    "name": "Anbu Selvam",
    "relationship": "daughter",
    "dob": (date.today() - timedelta(days=10 * 365 + 183)).isoformat(),
    "gender": "female",
    "annual_income": None,  # unknown until a real income is provided
    "is_student": True,
}


def publish_all_sample_schemes(db) -> None:
    from seed.load_schemes import seed_all

    seed_all(db)
    for scheme in db.query(Scheme).all():
        scheme.status = SchemeStatus.PUBLISHED
    db.commit()


def trigger_recompute(client) -> dict:
    response = client.post("/api/v1/eligibility/recompute")
    assert response.status_code == 200, response.text
    return response.json()


def _full_household_profile(client) -> None:
    response = client.put("/api/v1/me", json=PROFILE)
    assert response.status_code == 200, response.text


def test_requires_authentication(client) -> None:
    assert client.get("/api/v1/eligibility").status_code == 401
    assert client.get("/api/v1/eligibility/summary").status_code == 401
    assert client.post("/api/v1/eligibility/recompute").status_code == 401


def test_cards_for_completed_profile(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    response = logged_in_client.get("/api/v1/eligibility")
    assert response.status_code == 200, response.text
    body = response.json()

    slugs = {card["slug"] for card in body["cards"]}
    # No duplicate schemes (person "me" binds user-level and household rows).
    assert len(body["cards"]) == len(slugs)

    diabetes = next(card for card in body["cards"] if card["slug"] == "tn-free-diabetes-screening")
    assert diabetes["status"] == "eligible"
    assert diabetes["category"] == "healthcare"
    assert diabetes["department"].endswith("Government of Tamil Nadu")
    assert diabetes["level"] == "state"
    assert diabetes["benefit_type"] == "service"

    breakfast = next(
        card for card in body["cards"] if card["slug"] == "tn-morning-breakfast-scheme"
    )
    assert breakfast["status"] == "not_eligible"

    disability = next(card for card in body["cards"] if card["slug"] == "tn-disability-pension")
    assert disability["status"] == "needs_info"
    assert "is_disabled" in disability["missing_fields"]
    assert "Disability status" in disability["reason_line"]


def test_cards_summary_counts_match_cards(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    cards = logged_in_client.get("/api/v1/eligibility").json()
    summary = logged_in_client.get("/api/v1/eligibility/summary").json()
    me = next(person for person in summary["people"] if person["kind"] == "me")
    assert me["name"] == PROFILE["name"]
    counts = me["counts"]
    assert counts["total"] == cards["total"]
    assert counts["eligible"] == sum(
        1 for card in cards["cards"] if card["status"] == "eligible"
    )

    # Every family member is present in the summary, even without results.
    assert {person["kind"] for person in summary["people"]} == {"me"}


def test_filters(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    body = logged_in_client.get("/api/v1/eligibility", params={"category": "education"}).json()
    assert body["total"] > 0
    assert {card["category"] for card in body["cards"]} == {"education"}
    assert body["total"] < logged_in_client.get("/api/v1/eligibility").json()["total"]

    body = logged_in_client.get("/api/v1/eligibility", params={"scope": "family"}).json()
    assert body["total"] > 0
    assert {card["scope"] for card in body["cards"]} == {"family"}

    body = logged_in_client.get("/api/v1/eligibility", params={"status": "eligible"}).json()
    assert body["total"] > 0
    assert {card["status"] for card in body["cards"]} == {"eligible"}

    body = logged_in_client.get("/api/v1/eligibility", params={"scope": "everyone"})
    assert body.status_code == 422  # invalid scope is rejected


def test_pagination(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    first_page = logged_in_client.get(
        "/api/v1/eligibility", params={"limit": 2, "offset": 0}
    ).json()
    second_page = logged_in_client.get(
        "/api/v1/eligibility", params={"limit": 2, "offset": 2}
    ).json()
    assert first_page["total"] == second_page["total"] > 2
    first_ids = {card["scheme_id"] for card in first_page["cards"]}
    second_ids = {card["scheme_id"] for card in second_page["cards"]}
    assert first_ids.isdisjoint(second_ids)


def test_cards_sorted_high_first(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)
    trigger_recompute(logged_in_client)

    cards = logged_in_client.get("/api/v1/eligibility").json()["cards"]
    rank = {"high": 0, "medium": 1, "normal": 2}
    ranks = [rank[card["priority"]] for card in cards]
    assert ranks == sorted(ranks)


def test_days_and_priority_for_deadline_scheme(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    cards = logged_in_client.get("/api/v1/eligibility").json()["cards"]
    scholarship = next(
        card for card in cards if card["slug"] == "tn-first-graduate-scholarship"
    )
    assert scholarship["deadline"] == "2026-10-26"
    assert scholarship["days_remaining"] == (date(2026, 10, 26) - date.today()).days

    from app.eligibility.priority import priority_level

    expected = priority_level(
        days_remaining=scholarship["days_remaining"],
        benefit_amount=scholarship["benefit_amount"],
    )
    assert scholarship["priority"] == expected


def test_person_selector_member_results(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)
    member = logged_in_client.post("/api/v1/family", json=DAUGHTER).json()

    body = logged_in_client.get("/api/v1/eligibility", params={"person": member["id"]}).json()
    breakfast = next(
        card for card in body["cards"] if card["slug"] == "tn-morning-breakfast-scheme"
    )
    assert breakfast["status"] == "eligible"  # girl, 10, student, Tamil Nadu

    # Family-scope schemes do not appear on a member's list.
    assert all(card["scope"] != "family" for card in body["cards"])

    summary = logged_in_client.get("/api/v1/eligibility/summary").json()
    kinds = {person["kind"]: person["counts"]["total"] for person in summary["people"]}
    # 14 individual schemes apply per person; "me" also sees the household
    # schemes (8 family) → 22 rows in total.
    assert kinds["me"] == 22
    assert kinds["family"] == 14


def test_unknown_person_is_rejected(logged_in_client, make_logged_in_client) -> None:
    other = make_logged_in_client("9123456780")
    other.put("/api/v1/me", json=PROFILE)
    other_member = other.post("/api/v1/family", json=DAUGHTER).json()

    body = logged_in_client.get(
        "/api/v1/eligibility", params={"person": other_member["id"]}
    )
    assert body.status_code == 404
    assert logged_in_client.get("/api/v1/eligibility", params={"person": "abc"}).status_code == 400


def test_household_income_needs_info_until_complete(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    member = logged_in_client.post("/api/v1/family", json=DAUGHTER).json()

    insurance = logged_in_client.get(
        "/api/v1/eligibility", params={"scope": "family"}
    ).json()["cards"]
    cm_card = next(
        card for card in insurance if card["slug"] == "tn-cm-comprehensive-health-insurance"
    )
    assert cm_card["status"] == "needs_info"
    assert "household_income" in cm_card["missing_fields"]

    # Completing the member's income via the real endpoint recomputes.
    updated = logged_in_client.patch(
        f"/api/v1/family/{member['id']}", json={"annual_income": 60000}
    ).json()
    assert updated["annual_income"] == 60000

    cm_card = next(
        card
        for card in logged_in_client.get(
            "/api/v1/eligibility", params={"scope": "family"}
        ).json()["cards"]
        if card["slug"] == "tn-cm-comprehensive-health-insurance"
    )
    assert cm_card["status"] == "eligible"
    assert cm_card["reason_line"].startswith("You qualify")


def test_family_delete_removes_member_results(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)
    member = logged_in_client.post("/api/v1/family", json=DAUGHTER).json()

    summary_before = logged_in_client.get("/api/v1/eligibility/summary").json()
    assert any(person["kind"] == "family" for person in summary_before["people"])

    assert (
        logged_in_client.delete(f"/api/v1/family/{member['id']}").status_code == 204
    )
    summary_after = logged_in_client.get("/api/v1/eligibility/summary").json()
    assert summary_after["people"] == [
        person for person in summary_after["people"] if person["kind"] == "me"
    ]


def test_recompute_is_idempotent(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)

    first = trigger_recompute(logged_in_client)
    # Profile save already ran a recompute, so nothing is new; but every
    # result row must be reported as re-confirmed (unchanged), never duplicated.
    assert first["created"] == 0
    assert first["updated"] == 0
    assert first["unchanged"] > 0

    second = trigger_recompute(logged_in_client)
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == first["unchanged"]


def test_unpublished_schemes_are_invisible(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    draft_slug = "tn-free-diabetes-screening"
    scheme = db.query(Scheme).filter(Scheme.slug == draft_slug).one()
    scheme.status = SchemeStatus.DRAFT
    db.commit()

    _full_household_profile(logged_in_client)
    slugs = {card["slug"] for card in logged_in_client.get("/api/v1/eligibility").json()["cards"]}
    assert draft_slug not in slugs
    summary = logged_in_client.get("/api/v1/eligibility/summary").json()
    assert summary["people"][0]["counts"]["total"] < 22


def test_new_scheme_gains_eligibility_after_publish(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)
    _full_household_profile(logged_in_client)
    member = logged_in_client.post("/api/v1/family", json=DAUGHTER).json()

    # A newly published scholarship for students aged 10-12 with a deadline
    # eight days out: high priority, eligible for the daughter.
    deadline = date.today() + timedelta(days=8)
    db.add(
        Scheme(
            slug="sample-new-scholarship",
            name="Sample New Scholarship",
            department="Test Department",
            level="state",
            state="Tamil Nadu",
            category="education",
            scope="individual",
            benefit_summary="One-time grant for school-going children.",
            benefit_amount="INR 12000",
            benefit_type="cash",
            eligibility_rules={
                "applies_to": "individual",
                "rules": {
                    "all": [
                        {"field": "is_student", "op": "==", "value": True},
                        {"field": "age", "op": "between", "value": [10, 12]},
                        {"field": "state", "op": "==", "value": "Tamil Nadu"},
                    ]
                },
            },
            required_documents=[{"name": "Aadhaar card"}],
            application_steps=[
                {"order": 1, "title": "Apply", "description": "Submit the form."}
            ],
            deadline=deadline,
            status=SchemeStatus.PUBLISHED,  # publish hook in Phase 6 calls recompute
            priority=1,
            last_verified_on=date.today(),
            source_url="https://example.gov.in/",
        )
    )
    db.commit()
    trigger_recompute(logged_in_client)

    cards = logged_in_client.get(
        "/api/v1/eligibility", params={"person": member["id"]}
    ).json()["cards"]
    card = next(card for card in cards if card["slug"] == "sample-new-scholarship")
    assert card["status"] == "eligible"
    assert card["priority"] == "high"
    assert card["days_remaining"] == 8


def test_farmer_pension_age_boundary(logged_in_client, db) -> None:
    publish_all_sample_schemes(db)

    # Exactly 40 years old on the day the test runs.
    forty_years_ago = (date.today() - timedelta(days=40 * 365 + 10)).isoformat()
    response = logged_in_client.put("/api/v1/me", json={**PROFILE, "dob": forty_years_ago})
    assert response.status_code == 200

    cards = logged_in_client.get("/api/v1/eligibility").json()["cards"]
    maandhan = next(card for card in cards if card["slug"] == "pm-farmer-pension-maandhan")
    assert maandhan["status"] == "eligible"
