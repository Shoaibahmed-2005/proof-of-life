"""Column types and time helpers shared by the models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.types import DateTime, TypeDecorator


def utcnow() -> datetime:
    """Timezone-aware current UTC time. Use this everywhere instead of datetime.now()."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """
    Stores datetimes as naive UTC (SQLite has no timezone support) and always
    returns timezone-aware UTC datetimes, so comparisons with utcnow() are safe.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UTCDateTime requires timezone-aware datetimes")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
