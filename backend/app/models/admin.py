"""Admin staff accounts (board-phase 6).

Completely separate from the citizen OTP login: username + password hash
(PBKDF2-HMAC-SHA256) + a TOTP secret for 2FA. Roles:
``editor`` can draft and edit; ``publisher`` can do that plus publish
schemes and dispatch bulk alerts.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow
from app.models.types import EncryptedString


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # PBKDF2 hash: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    # "editor" or "publisher"
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="editor")
    # Base32 TOTP seed (stored encrypted like other sensitive fields).
    totp_secret: Mapped[str] = mapped_column(EncryptedString(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:
        return f"<AdminUser id={self.id} username={self.username!r} role={self.role}>"
