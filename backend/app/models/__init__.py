"""Model package. Importing this module registers every table on ``Base.metadata``."""

from __future__ import annotations

from app.models.admin import AdminUser
from app.models.analytics import AnalyticsEvent
from app.models.audit import AdminAuditLog
from app.models.base import Base, TimestampMixin, utcnow
from app.models.chat import ChatMessage
from app.models.eligibility import EligibilityResult
from app.models.facility import Facility
from app.models.family import FamilyMember
from app.models.notification import Notification
from app.models.otp import OtpRequest
from app.models.refresh_token import RefreshToken
from app.models.scheme import Scheme, SchemeTranslation
from app.models.user import User

__all__ = [
    "AdminAuditLog",
    "AdminUser",
    "AnalyticsEvent",
    "Base",
    "ChatMessage",
    "EligibilityResult",
    "Facility",
    "FamilyMember",
    "Notification",
    "OtpRequest",
    "RefreshToken",
    "Scheme",
    "SchemeTranslation",
    "TimestampMixin",
    "User",
    "utcnow",
]
