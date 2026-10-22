"""Reference data for form dropdowns (states, districts)."""

from __future__ import annotations

from fastapi import APIRouter

from app.reference.locations import DISTRICTS_BY_STATE, INDIAN_STATES_AND_UTS

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/locations", summary="States and known districts")
def locations() -> dict[str, object]:
    return {
        "states": list(INDIAN_STATES_AND_UTS),
        "districts_by_state": {
            state: list(districts) for state, districts in DISTRICTS_BY_STATE.items()
        },
    }
