"""Enumerations shared by models, schemas, and the seed pipeline.

All enums are stored as VARCHAR with a CHECK constraint (``native_enum=False``)
rather than MySQL's native ENUM type. This keeps Alembic migrations reversible
and lets values be added without a table rebuild.
"""

from __future__ import annotations

from enum import StrEnum


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class Relationship(StrEnum):
    SELF = "self"
    SPOUSE = "spouse"
    SON = "son"
    DAUGHTER = "daughter"
    FATHER = "father"
    MOTHER = "mother"
    BROTHER = "brother"
    SISTER = "sister"
    GRANDFATHER = "grandfather"
    GRANDMOTHER = "grandmother"
    OTHER = "other"


class EducationLevel(StrEnum):
    NO_FORMAL = "no_formal"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    HIGHER_SECONDARY = "higher_secondary"
    ITI = "iti"
    DIPLOMA = "diploma"
    UNDERGRADUATE = "undergraduate"
    POSTGRADUATE = "postgraduate"
    OTHER = "other"


class MaritalStatus(StrEnum):
    SINGLE = "single"
    MARRIED = "married"
    WIDOWED = "widowed"
    DIVORCED = "divorced"
    SEPARATED = "separated"


class Language(StrEnum):
    ENGLISH = "en"
    TAMIL = "ta"
    HINDI = "hi"
    TELUGU = "te"
    KANNADA = "kn"
    MALAYALAM = "ml"


class SchemeLevel(StrEnum):
    CENTRAL = "central"
    STATE = "state"


class SchemeScope(StrEnum):
    INDIVIDUAL = "individual"
    FAMILY = "family"


class SchemeStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class BenefitType(StrEnum):
    CASH = "cash"
    IN_KIND = "in_kind"
    SUBSIDY = "subsidy"
    SERVICE = "service"
    INSURANCE = "insurance"
    PENSION = "pension"
    LOAN = "loan"
    OTHER = "other"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    NOT_ELIGIBLE = "not_eligible"
    NEEDS_INFO = "needs_info"


class FacilityType(StrEnum):
    CSC = "csc"
    TALUK_OFFICE = "taluk_office"
    COLLECTOR_OFFICE = "collector_office"
    E_SEVAI = "e_sevai"
    WELFARE_OFFICE = "welfare_office"


class NotificationType(StrEnum):
    SCHEME_SUMMARY = "scheme_summary"
    NEW_SCHEME_ELIGIBLE = "new_scheme_eligible"
    FAMILY_MILESTONE = "family_milestone"
    DEADLINE_REMINDER = "deadline_reminder"
    FESTIVAL_BENEFIT = "festival_benefit"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
