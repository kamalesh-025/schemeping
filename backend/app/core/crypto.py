"""Fernet encryption for sensitive database columns.

Design notes:
- Encryption happens at the application layer, before the value reaches MySQL.
- Fernet authenticates as well as encrypts, so tampered ciphertext fails loudly.
- Multiple keys are supported for rotation: the first key encrypts, all keys
  are tried when decrypting.
- Encrypted columns cannot be filtered or indexed in SQL by design. Anything
  that needs to be queried (e.g. ``users.mobile``) stays unencrypted, and age
  based work is computed in Python from the decrypted date of birth.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

_ENVELOPE_VERSION = 1


class DecryptionError(RuntimeError):
    """Raised when stored ciphertext cannot be decrypted with any configured key."""


def _load_keys(raw: str) -> list[str]:
    keys = [part.strip() for part in raw.split(",") if part.strip()]
    if not keys:
        raise ValueError("ENCRYPTION_KEY is empty; at least one Fernet key is required")
    return keys


@lru_cache
def _fernet() -> MultiFernet:
    settings = get_settings()
    keys = _load_keys(settings.encryption_key)
    return MultiFernet([Fernet(key.encode("utf-8")) for key in keys])


def encrypt_text(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Stored value could not be decrypted. Check ENCRYPTION_KEY rotation."
        ) from exc


def _encode(value: Any) -> str:
    if isinstance(value, bool):
        tagged = {"t": "bool", "v": value}
    elif isinstance(value, int):
        tagged = {"t": "int", "v": value}
    elif isinstance(value, float):
        tagged = {"t": "float", "v": value}
    elif isinstance(value, datetime):
        tagged = {"t": "datetime", "v": value.isoformat()}
    elif isinstance(value, date):
        tagged = {"t": "date", "v": value.isoformat()}
    elif isinstance(value, str):
        tagged = {"t": "str", "v": value}
    else:  # pragma: no cover - defensive, the column types are known
        raise TypeError(f"Unsupported type for encrypted column: {type(value)!r}")

    return json.dumps({"v": _ENVELOPE_VERSION, **tagged}, separators=(",", ":"))


def _decode(payload: str) -> Any:
    data = json.loads(payload)
    kind = data.get("t")
    raw = data.get("v")
    if kind == "bool":
        return bool(raw)
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "datetime":
        return datetime.fromisoformat(raw)
    if kind == "date":
        return date.fromisoformat(raw)
    if kind == "str":
        return str(raw)
    raise DecryptionError(f"Unknown encrypted envelope type: {kind!r}")


def encrypt_value(value: Any) -> str | None:
    if value is None:
        return None
    return encrypt_text(_encode(value))


def decrypt_value(ciphertext: str | None) -> Any:
    if ciphertext is None:
        return None
    return _decode(decrypt_text(ciphertext))
