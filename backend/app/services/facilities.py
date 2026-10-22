"""Facility lookup and distance ordering.

``locate_facilities`` returns plain dictionaries shaped like ``FacilityOut``
so the router never touches geometry internals. The nearest query orders by
MySQL's ``ST_Distance_Sphere``; the query point is built with the same
``axis-order=long-lat`` convention as ``PointType`` binds, otherwise MySQL
silently swaps latitude and longitude for SRID 4326.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import FacilityType
from app.models.facility import Facility
from app.services.eligibility import _enum_value

_METERS_PER_KM = 1000.0


def locate_facilities(
    db: Session,
    *,
    lat: float | None = None,
    lon: float | None = None,
    types: list[FacilityType] | None = None,
    district: str | None = None,
    pincode: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Absolute nearest-first with coordinates; filtered otherwise."""
    if (lat is None) != (lon is None):
        raise ValueError("Provide both lat and lon, or neither.")

    conditions: list[Any] = []
    if types:
        conditions.append(Facility.type.in_(types))
    if district:
        conditions.append(Facility.district == district)
    if pincode:
        conditions.append(Facility.pincode == pincode)

    def _payload(facility: Facility, distance_metres: float | None) -> dict[str, Any]:
        lon, lat = facility.location
        return {
            "id": facility.id,
            "name": facility.name,
            "type": _enum_value(facility.type),
            "address": facility.address,
            "district": facility.district,
            "state": facility.state,
            "pincode": facility.pincode,
            "phone": facility.phone,
            "working_hours": facility.working_hours,
            "lat": round(lat, 6),
            "lon": round(lon, 6),            "distance_km": (
                round(float(distance_metres) / _METERS_PER_KM, 2)
                if distance_metres is not None
                else None
            ),
        }

    if lat is not None and lon is not None:
        point = func.ST_GeomFromText(f"POINT({lon} {lat})", 4326, "axis-order=long-lat")
        distance_expr = func.ST_Distance_Sphere(Facility.location, point)
        selection = (
            select(Facility, distance_expr.label("distance"))
            .where(*conditions)
            .order_by(distance_expr, Facility.id)
            .limit(limit)
        )
        return [_payload(facility, distance) for facility, distance in db.execute(selection).all()]

    facilities = db.scalars(
        select(Facility).where(*conditions).order_by(Facility.name, Facility.id).limit(limit)
    ).all()
    return [_payload(facility, None) for facility in facilities]
