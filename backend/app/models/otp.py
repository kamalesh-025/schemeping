"""One-time password requests (hash only, never the plaintext OTP)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class OtpRequest(Base):
    __tablename__ = "otp_requests"
    __table_args__ = (
        Index("ix_otp_requests_mobile_created", "mobile", "created_at"),
        Index("ix_otp_requests_ip_created", "ip_address", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    mobile: Mapped[str] = mapped_column(String(15), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(45))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:
        return f"<OtpRequest id={self.id} expires_at={self.expires_at}>"
