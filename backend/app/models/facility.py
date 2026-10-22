"""Government facilities used for last-mile guidance."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import FacilityType
from app.models.types import PointType, enum_type


class Facility(TimestampMixin, Base):
    """A physical office a citizen can visit.

    ``location`` is the source of truth: a MySQL ``POINT`` with SRID 4326
    (WGS84) and a SPATIAL index. Latitude and longitude are exposed as Python
    properties so callers never have to parse WKT.
    """

    __tablename__ = "facilities"
    __table_args__ = (
        Index("ix_facilities_district_state", "district", "state"),
        Index("ix_facilities_type", "type"),
        Index("ix_facilities_location", "location", mysql_prefix="SPATIAL"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(250), nullable=False)
    type: Mapped[FacilityType] = mapped_column(
        enum_type(FacilityType), nullable=False
    )

    address: Mapped[str] = mapped_column(String(500), nullable=False)
    district: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[str | None] = mapped_column(String(10))
    phone: Mapped[str | None] = mapped_column(String(30))
    working_hours: Mapped[str | None] = mapped_column(String(250))

    location: Mapped[Any] = mapped_column(PointType, nullable=False)

    verified_on: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(500))
    # Stable identity for idempotent seeding across environments.
    external_ref: Mapped[str | None] = mapped_column(String(150), unique=True)

    def __repr__(self) -> str:
        return f"<Facility id={self.id} name={self.name!r}>"

    @property
    def longitude(self) -> float:
        return float(self.location[0])

    @property
    def latitude(self) -> float:
        return float(self.location[1])
