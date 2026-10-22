"""Admin authentication: PBKDF2 passwords, RFC 6238 TOTP, short-JWT tokens.

Citizen login uses mobile OTP; this is the completely separate staff
login required by AGENTS.md 12. Every successful login and later write is
recorded in ``admin_audit_logs`` by the API layer.

Standard library only: ``hashlib.pbkdf2_hmac`` for passwords (no passlib
dependency) and an HMAC-SHA1 based RFC 6238 TOTP implementation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_PBKDF2_ITERATIONS = 200_000
_TOTP_STEP = 30
_TOTP_DIGITS = 6
_TOTP_DRIFT = 1  # accept the previous/next 30s window (clock skew)

_ROLES = ("editor", "publisher")
# editor can draft and edit; publisher additionally publishes and alerts.
_ROLE_RANK = {"editor": 0, "publisher": 1}


class AdminAuthError(Exception):
    """Wrong username, password, TOTP, or role."""


# ------------------------------------------------------------------ passwords


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _scheme, iterations_hex, salt_hex, hash_hex = stored.split("$")
        iterations = int(iterations_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


# ------------------------------------------------------------------ TOTP


def generate_totp_secret() -> str:
    """A 160-bit base32 seed, ready for authenticator apps / provisioning."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_provisioning_uri(secret: str, username: str, issuer: str = "SchemePing") -> str:
    label = f"{issuer}:{username}"
    params = f"secret={secret}&issuer={issuer}&digits={_TOTP_DIGITS}&period={_TOTP_STEP}"
    return f"otpauth://totp/{label}?{params}&algorithm=SHA1"


def _totp_code(secret_b32: str, counter: int) -> str:
    padding = "=" * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode(secret_b32.upper() + padding)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (
        struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    ) % 10**_TOTP_DIGITS
    return f"{code:0{_TOTP_DIGITS}d}"


def verify_totp(secret: str, code: str, *, at: float | None = None) -> bool:
    """Constant-time verification over a ±30s drift window."""
    provided = code.strip().replace(" ", "")
    if not provided.isdigit() or len(provided) != _TOTP_DIGITS:
        return False
    now = time.time() if at is None else at
    counter = int(now // _TOTP_STEP)
    for offset in range(-_TOTP_DRIFT, _TOTP_DRIFT + 1):
        candidate = _totp_code(secret, counter + offset)
        if hmac.compare_digest(candidate, provided):
            return True
    return False


# ------------------------------------------------------------------ tokens


def create_admin_token(username: str) -> str:
    settings = get_settings()
    issued_at = datetime.now(tz=UTC)
    payload = {
        "sub": username,
        "type": "admin",
        "iat": int(issued_at.timestamp()),
        "exp": int(
            (issued_at + timedelta(minutes=settings.admin_token_ttl_minutes)).timestamp()
        ),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_admin_token(token: str) -> str:
    """The admin username, or raises ``AdminAuthError``."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise AdminAuthError("Invalid or expired admin token") from exc
    if payload.get("type") != "admin":
        raise AdminAuthError("Not an admin token")
    return str(payload.get("sub", ""))


def role_allowed(role: str, needed: str) -> bool:
    return (
        role in _ROLE_RANK
        and needed in _ROLE_RANK
        and _ROLE_RANK[role] >= _ROLE_RANK[needed]
    )


def normalise_role(role: str) -> str:
    if role not in _ROLES:
        raise AdminAuthError(f"Unknown role: {role}")
    return role


def audit_diff(before: Any, after: Any) -> dict[str, Any]:
    """Shallow field-level diff for ``admin_audit_logs``."""
    if before is None:
        return {"created": after}
    if after is None:
        return {"deleted": before}
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"before": before.get(key), "after": after.get(key)}
    return {"changed": changes} if changes else {"unchanged": True}
