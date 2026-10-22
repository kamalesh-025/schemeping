"""Token, OTP and password primitives.

Three kinds of credentials exist:

- **Access token**: a short-lived JWT signed with ``SECRET_KEY`` (HS256). It is
  stateless and carries only the user id, so it can be verified without a
  database round trip.
- **Refresh token**: an opaque 256-bit random string. Only its SHA-256 hash is
  stored, so a database leak does not hand out sessions. Refresh tokens rotate
  on every use; reuse of an already-rotated token revokes the whole family.
- **Password**: hashed with ``hashlib.scrypt`` (stdlib, memory-hard). The
  parameters are stored inside the hash string, so they can be raised later and
  old hashes are upgraded on the next successful login.

OTPs are hashed with HMAC-SHA256 keyed by ``SECRET_KEY`` so that the database
never stores a value that can be brute-forced offline with a rainbow table.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
OTP_HASH_CONTEXT = b"schemeping-otp-v1"

# scrypt cost: 16 MiB, roughly 30-60 ms on the target ARM VM. Raising N later is
# safe because the value used is read back from each stored hash.
PASSWORD_SCHEME = "scrypt"
PASSWORD_N = 2**14
PASSWORD_R = 8
PASSWORD_P = 1
PASSWORD_DKLEN = 32
_PASSWORD_MAX_N = 2**15  # refuse absurd parameters from a corrupted row


class TokenError(Exception):
    """Raised when a JWT is missing, malformed, expired, or has the wrong type."""


def _settings() -> Any:
    return get_settings()


def create_access_token(user_id: int, *, now: datetime | None = None) -> str:
    settings = _settings()
    issued_at = now or datetime.now(tz=UTC)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "iat": int(issued_at.timestamp()),
        "exp": int(
            (issued_at + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()
        ),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int:
    """Return the user id, or raise ``TokenError``."""
    settings = _settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise TokenError("Invalid or expired access token") from exc

    if payload.get("type") != "access":
        raise TokenError("Not an access token")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("Malformed access token subject") from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_otp(length: int) -> str:
    """Cryptographically random numeric OTP, zero-padded to ``length``."""
    upper = 10**length
    return f"{secrets.randbelow(upper):0{length}d}"


def hash_otp(mobile: str, otp: str) -> str:
    settings = _settings()
    message = f"{mobile}:{otp}".encode()
    return hmac.new(
        settings.secret_key.encode("utf-8"), OTP_HASH_CONTEXT + message, hashlib.sha256
    ).hexdigest()


def otp_matches(mobile: str, otp: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(mobile, otp), stored_hash)


def hash_password(password: str) -> str:
    """Return ``scrypt$N$r$p$salt$hash`` for storage in ``users.password_hash``."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_N,
        r=PASSWORD_R,
        p=PASSWORD_P,
        dklen=PASSWORD_DKLEN,
    )
    return "$".join(
        (
            PASSWORD_SCHEME,
            str(PASSWORD_N),
            str(PASSWORD_R),
            str(PASSWORD_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, stored: str | None) -> bool:
    """Constant-time check of a password against a stored hash.

    A missing or malformed hash is a failed login, never an exception: legacy
    OTP-only accounts have no password, and a corrupted row must not 500.
    """
    if not stored:
        return False

    try:
        scheme, n_raw, r_raw, p_raw, salt_raw, digest_raw = stored.split("$")
        if scheme != PASSWORD_SCHEME:
            return False
        n, r, p = int(n_raw), int(r_raw), int(p_raw)
        if not (2**12 <= n <= _PASSWORD_MAX_N) or not (1 <= r <= 32) or not (1 <= p <= 16):
            return False
        salt = base64.b64decode(salt_raw, validate=True)
        expected = base64.b64decode(digest_raw, validate=True)
        if not 16 <= len(expected) <= 64:
            return False
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
    except (ValueError, TypeError, OverflowError):
        return False

    return hmac.compare_digest(actual, expected)


def password_needs_rehash(stored: str | None) -> bool:
    """True when a hash was produced with weaker parameters than today's."""
    if not stored:
        return True
    parts = stored.split("$")
    current = [
        PASSWORD_SCHEME,
        str(PASSWORD_N),
        str(PASSWORD_R),
        str(PASSWORD_P),
    ]
    return parts[:4] != current


# Used to spend the same time on an unknown mobile number as on a wrong
# password, so response timing does not reveal which accounts exist.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(24))


def mask_mobile(mobile: str) -> str:
    """``9876543210`` -> ``98******10``. Safe for logs."""
    digits = "".join(character for character in mobile if character.isdigit())
    if len(digits) < 4:
        return "****"
    return f"{digits[:2]}{'*' * (len(digits) - 4)}{digits[-2:]}"
