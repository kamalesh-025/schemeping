"""Public capability flags.

The frontend must not offer an action that cannot work in the current
deployment. Business-initiated WhatsApp delivery needs Meta/MSG91 credentials
plus approved templates; without them SchemePing still lets the citizen send a
scheme summary through the free ``wa.me`` click-to-chat link, which opens on
their own phone and needs no provider.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.messaging import whatsapp_delivery_configured

router = APIRouter(tags=["features"])


class FeaturesOut(BaseModel):
    whatsapp_delivery: bool
    whatsapp_click_to_chat: bool = True


@router.get("/features", response_model=FeaturesOut, summary="Runtime capabilities")
def features() -> FeaturesOut:
    return FeaturesOut(whatsapp_delivery=whatsapp_delivery_configured())
