"""Facilities endpoints: nearest by coordinates, or fallback lookup.

Both endpoints sit behind the user session. ``/facilities/nearest`` orders
by ``ST_Distance_Sphere`` (metres) and converts to kilometres in the service
so the UI never has to. ``/facilities`` supports district and pincode
filtering when browser geolocation is denied or unavailable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession
from app.models.enums import FacilityType
from app.schemas.scheme import FacilitiesOut, FacilityOut
from app.services.facilities import locate_facilities

router = APIRouter(prefix="/facilities", tags=["facilities"])


@router.get("/nearest", response_model=FacilitiesOut, summary="Nearest facilities")
def nearest_facilities(
    user: CurrentUser,
    db: DbSession,
    lat: Annotated[float, Query(ge=-90, le=90, description="Device latitude")],
    lon: Annotated[float, Query(ge=-180, le=180, description="Device longitude")],
    type: list[FacilityType] | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> FacilitiesOut:
    facilities = locate_facilities(db, lat=lat, lon=lon, types=type, limit=limit)
    return FacilitiesOut(
        total=len(facilities),
        facilities=[FacilityOut.model_validate(item) for item in facilities],
    )


@router.get("", response_model=FacilitiesOut, summary="Find facilities by district")
def find_facilities(
    user: CurrentUser,
    db: DbSession,
    district: Annotated[str | None, Query(max_length=100)] = None,
    pincode: Annotated[str | None, Query(max_length=10, pattern=r"^\d+$")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> FacilitiesOut:
    if not district and not pincode:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Provide a district or a pincode to search facilities.",
        )
    facilities = locate_facilities(db, district=district, pincode=pincode, limit=limit)
    return FacilitiesOut(
        total=len(facilities),
        facilities=[FacilityOut.model_validate(item) for item in facilities],
    )
