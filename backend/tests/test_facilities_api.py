"""Facilities endpoints: distance ordering, filters, and fallback lookup."""

from __future__ import annotations

from app.models.facility import Facility
from fastapi.testclient import TestClient


def make_facility(db, ref: str, name: str, lat: float, lon: float, **extra) -> Facility:
    facility = Facility(
        external_ref=ref,
        name=name,
        type=extra.get("type") or "e_sevai",
        address=extra.get("address") or f"Sample address, {name}",
        district=extra.get("district") or "Erode",
        state="Tamil Nadu",
        pincode=extra.get("pincode"),
        phone=extra.get("phone"),
        working_hours=extra.get("working_hours") or "Mon-Fri 10am-5pm",
        location=(lon, lat),
    )
    db.add(facility)
    db.commit()
    db.refresh(facility)
    return facility


# Query point: Erode city centre-ish. Offsets are known approximations:
# 1 degree of latitude ~ 111 km.
def test_nearest_orders_by_distance(logged_in_client: TestClient, db):
    make_facility(db, "f-far", "Facility far", 11.0, 77.73)   # ~130 km north
    make_facility(db, "f-mid", "Facility mid", 11.4, 77.73)   # ~62 km north
    make_facility(db, "f-near", "Facility near", 11.35, 77.73)  # ~7 km north

    response = logged_in_client.get(
        "/api/v1/facilities/nearest", params={"lat": 11.3440, "lon": 77.7280}
    )
    assert response.status_code == 200, response.text
    names = [item["name"] for item in response.json()["facilities"]]
    assert names == ["Facility near", "Facility mid", "Facility far"]

    distances = [item["distance_km"] for item in response.json()["facilities"]]
    assert distances[0] is not None
    assert distances[0] < distances[1] < distances[2]


def test_nearest_respects_type_filter_and_limit(logged_in_client: TestClient, db):
    make_facility(db, "f-a", "Sevai centre", 11.345, 77.729, type="e_sevai")
    make_facility(db, "f-b", "Collectorate", 11.346, 77.731, type="collector_office")
    make_facility(db, "f-c", "Other sevai", 11.347, 77.732, type="e_sevai")

    response = logged_in_client.get(
        "/api/v1/facilities/nearest",
        params={"lat": 11.3440, "lon": 77.7280, "type": "e_sevai", "limit": 1},
    )
    body = response.json()
    assert body["total"] == 1
    assert body["facilities"][0]["name"] == "Sevai centre"

    everything = logged_in_client.get(
        "/api/v1/facilities/nearest", params={"lat": 11.3440, "lon": 77.7280, "limit": 10}
    )
    assert everything.json()["total"] == 3


def test_nearest_requires_authentication(client: TestClient, db):
    response = client.get("/api/v1/facilities/nearest", params={"lat": 11.34, "lon": 77.73})
    assert response.status_code == 401


def test_facilities_by_district_returns_matches(logged_in_client: TestClient, db):
    make_facility(db, "f-d1", "Erode sevai", 11.34, 77.73, district="Erode", pincode="638001")
    make_facility(db, "f-d2", "Madurai sevai", 9.92, 78.12, district="Madurai", pincode="625020")

    response = logged_in_client.get(
        "/api/v1/facilities", params={"district": "Erode"}
    )
    body = response.json()
    assert body["total"] == 1
    assert body["facilities"][0]["name"] == "Erode sevai"
    assert body["facilities"][0]["distance_km"] is None


def test_facilities_by_pincode(logged_in_client: TestClient, db):
    make_facility(db, "f-p1", "Perundurai centre", 11.34, 77.63, pincode="638052")
    make_facility(db, "f-p2", "Town centre", 11.34, 77.73, pincode="638001")

    response = logged_in_client.get(
        "/api/v1/facilities", params={"pincode": "638052"}
    )
    assert response.json()["facilities"][0]["name"] == "Perundurai centre"


def test_facilities_requires_district_or_pincode(logged_in_client: TestClient):
    assert logged_in_client.get("/api/v1/facilities").status_code == 400


def test_nearest_rejects_missing_coordinate(logged_in_client: TestClient):
    response = logged_in_client.get("/api/v1/facilities/nearest", params={"lat": 11.34})
    assert response.status_code == 422


def test_facility_payload_fields(logged_in_client: TestClient, db):
    make_facility(
        db,
        "f-fields",
        "Field facility",
        11.344,
        77.730,
        phone="+91-424-0000006",
        working_hours="Mon-Sat 9am-6pm",
        pincode="638009",
        type="welfare_office",
    )
    body = logged_in_client.get(
        "/api/v1/facilities/nearest", params={"lat": 11.3440, "lon": 77.7280}
    ).json()["facilities"][0]
    assert body["type"] == "welfare_office"
    assert body["phone"] == "+91-424-0000006"
    assert body["working_hours"] == "Mon-Sat 9am-6pm"
    assert body["pincode"] == "638009"
    assert body["district"] == "Erode"
    assert body["distance_km"] > 0
