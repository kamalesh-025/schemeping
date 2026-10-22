"""Shared column types: encrypted scalars and a MySQL POINT."""

from __future__ import annotations

import struct
from enum import Enum as PyEnum
from typing import Any

from sqlalchemy import Enum as SAEnum
from sqlalchemy import func
from sqlalchemy.types import Text, TypeDecorator, UserDefinedType

from app.core.crypto import decrypt_value, encrypt_value


def enum_type[E: PyEnum](enum_cls: type[E], length: int = 32) -> SAEnum:
    """VARCHAR-backed enum that stores the member *value* (``"en"``), not its name.

    ``native_enum=False`` keeps migrations reversible and avoids MySQL's ALTER
    TABLE enum rebuild whenever a value is added. A CHECK constraint is still
    generated, so the database rejects unknown values.
    """

    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
    )


class EncryptedString(TypeDecorator[Any]):
    """Application-level encrypted value stored as TEXT.

    Accepts and returns ``str | int | float | bool | date | datetime | None``.
    The declared Python type on the model (e.g. ``Mapped[date | None]``) is the
    real contract; the database only ever sees authenticated ciphertext.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        return encrypt_value(value)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return decrypt_value(str(value))


class PointType(UserDefinedType[Any]):
    """MySQL ``POINT SRID 4326``.

    Python value is a ``(longitude, latitude)`` tuple.

    - Bind: emits ``ST_GeomFromText('POINT(lon lat)', 4326, 'axis-order=long-lat')``.
      MySQL's EPSG:4326 default axis order is latitude-first; without the
      explicit axis order, longitude and latitude are silently swapped.
    - Result: MySQL returns the internal geometry format (4-byte SRID followed
      by little-endian WKB). Parsing those 25 bytes directly is deterministic
      and avoids a per-row ``ST_AsText`` call. X is longitude, Y is latitude.
    """

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "POINT SRID 4326"

    def bind_processor(self, dialect: Any) -> Any:
        def process(value: Any) -> str | None:
            if value is None:
                return None
            longitude, latitude = value
            return f"POINT({longitude} {latitude})"

        return process

    def bind_expression(self, bindvalue: Any) -> Any:
        return func.ST_GeomFromText(bindvalue, 4326, "axis-order=long-lat")

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        def process(value: Any) -> tuple[float, float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                # Already WKT (e.g. a SELECT that used ST_AsText explicitly).
                body = value[value.index("(") + 1 : value.index(")")]
                longitude, latitude = (float(part) for part in body.split())
                return (longitude, latitude)

            raw = bytes(value)
            if len(raw) < 25 or raw[4] != 1:
                raise ValueError(f"Unexpected MySQL geometry payload: {raw!r}")
            longitude = struct.unpack_from("<d", raw, 9)[0]
            latitude = struct.unpack_from("<d", raw, 17)[0]
            return (longitude, latitude)

        return process
