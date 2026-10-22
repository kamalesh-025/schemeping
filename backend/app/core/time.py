"""Timezone helpers.

MySQL ``DATETIME`` columns lose their timezone on the round trip even when the
SQLAlchemy column is declared ``DateTime(timezone=True)``. Every comparison in
application code must therefore normalise stored values to UTC-aware datetimes
first.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30), name="Asia/Kolkata")


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def age_on(dob: date, today: date) -> int:
    """Whole years between ``dob`` and ``today`` (never negative)."""
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(years, 0)


def ist_now() -> datetime:
    """The current time in India: quiet hours are defined in IST."""
    return datetime.now(tz=IST)


def quiet_hours_delay(
    now: datetime | None = None, *, start_hour: int = 21, end_hour: int = 8
) -> timedelta | None:
    """Delay until 8 AM IST if ``now`` falls inside the 9 PM-8 AM IST window.

    Non-urgent proactive notifications are held (not dropped) and released
    at the next 8 AM IST.
    """
    moment = (now or ist_now()).astimezone(IST)
    if start_hour <= moment.hour < 24 or 0 <= moment.hour < end_hour:
        release = moment.replace(hour=end_hour, minute=0, second=0, microsecond=0)
        if moment.hour >= start_hour:
            release += timedelta(days=1)
        moment_utc = moment.astimezone(UTC)
        return release.astimezone(UTC) - moment_utc
    return None


def utc_to_ist(value: datetime) -> datetime:
    return value.astimezone(IST)
