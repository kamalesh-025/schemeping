"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Gender, Language
from app.schemas.validators import (
    ValidationMessage,
    is_valid_mobile,
    normalise_mobile,
)


class MobileIn(BaseModel):
    mobile: str = Field(min_length=10, max_length=16)

    @field_validator("mobile")
    @classmethod
    def _valid_mobile(cls, value: str) -> str:
        normalised = normalise_mobile(value)
        if not is_valid_mobile(normalised):
            raise ValueError(ValidationMessage.MOBILE)
        return normalised


class OtpRequestIn(MobileIn):
    pass


class OtpRequestOut(BaseModel):
    message: str
    expires_in_seconds: int
    resend_after_seconds: int


class OtpVerifyIn(MobileIn):
    otp: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


def _check_password(value: str) -> str:
    """Shared password policy for registration and password changes."""
    from app.core.config import get_settings

    minimum = get_settings().password_min_length
    if len(value) < minimum:
        raise ValueError(f"Use at least {minimum} characters for your password.")
    if len(value) > 128:
        raise ValueError("Use at most 128 characters for your password.")
    if not value.strip():
        raise ValueError("Your password cannot be only spaces.")
    return value


class RegisterIn(MobileIn):
    """Create an account with a mobile number and a password."""

    password: str = Field(max_length=128)
    name: str | None = Field(default=None, max_length=150)

    _validate_password = field_validator("password")(_check_password)

    @field_validator("name")
    @classmethod
    def _blank_name_is_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LoginIn(MobileIn):
    # No minimum here: an old (or wrong) password must fail authentication with
    # the same message, not fail validation with a hint about its shape.
    password: str = Field(min_length=1, max_length=128)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(max_length=128)

    _validate_password = field_validator("new_password")(_check_password)


class AuthConfigOut(BaseModel):
    """Tells the SPA which sign-in flow to render.

    ``password`` is the default (no SMS vendor). ``server`` is the classic OTP
    flow (our backend sends and verifies the code). ``widget`` means MSG91's OTP
    widget runs in the browser and the client trades its access token for a
    session. The widget fields are public by design (they ship in the widget's
    client script); the auth key is not.
    """

    mode: Literal["password", "server", "widget"]
    password_min_length: int = 8
    widget_id: str | None = None
    widget_token: str | None = None


class OtpWidgetVerifyIn(BaseModel):
    """Access token minted by the MSG91 OTP widget after the user verifies."""

    access_token: str = Field(min_length=10, max_length=4096)


class UserSessionOut(BaseModel):
    """Returned by verify/refresh so the SPA can decide where to route."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    mobile: str
    language: Language
    profile_complete: bool
    has_consent: bool


class TokenPair(BaseModel):
    access_expires_in_seconds: int
    refresh_expires_in_seconds: int


class ConsentUpdateIn(BaseModel):
    whatsapp_opt_in: bool


class ConsentOut(BaseModel):
    data_processing: bool
    whatsapp_opt_in: bool
    consented_at: datetime | None
    whatsapp_opted_out_at: datetime | None
    policy_version: str | None


class MessageOut(BaseModel):
    message: str


class ProfileBasics(BaseModel):
    """Fields shared by onboarding validation checks."""

    name: str | None
    dob: date | None
    gender: Gender | None
    state: str | None
    district: str | None
