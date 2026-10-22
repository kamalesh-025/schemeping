"""Shared Pydantic validators."""

from __future__ import annotations

import re
from datetime import date

from app.core.time import utcnow

_MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
_PINCODE_RE = re.compile(r"^[1-9]\d{5}$")
_EARLIEST_DOB = date(1900, 1, 1)
_MAX_AGE_YEARS = 120


class ValidationMessage:
    MOBILE = "Enter a valid 10-digit Indian mobile number."
    PINCODE = "Enter a valid 6-digit PIN code."
    DOB_FUTURE = "Date of birth cannot be in the future."
    DOB_TOO_OLD = "Enter a date of birth after 1 January 1900."
    DOB_UNREALISTIC = "That date of birth looks unrealistic. Please check it."


def normalise_mobile(value: str) -> str:
    """Strip spaces, dashes, and a +91 / 0 prefix; return 10 digits."""
    digits = re.sub(r"\D", "", value)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def is_valid_mobile(value: str) -> bool:
    return bool(_MOBILE_RE.fullmatch(normalise_mobile(value)))


def is_valid_pincode(value: str) -> bool:
    return bool(_PINCODE_RE.fullmatch(value))


def validate_dob(value: date | None) -> date | None:
    if value is None:
        return None
    today = utcnow().date()
    if value > today:
        raise ValueError(ValidationMessage.DOB_FUTURE)
    if value < _EARLIEST_DOB:
        raise ValueError(ValidationMessage.DOB_TOO_OLD)
    if today.year - value.year > _MAX_AGE_YEARS:
        raise ValueError(ValidationMessage.DOB_UNREALISTIC)
    return value
