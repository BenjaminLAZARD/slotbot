"""Database tables (SQLAlchemy 2). Postgres in every environment; SQLite only in unit tests."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, TypeDecorator, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Always store UTC and always hand back timezone-aware datetimes, whatever the backend."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("naive datetime")
        return value.astimezone(UTC) if value else None

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: UTCDateTime, dict[str, Any]: JSON, list[Any]: JSON}


class Profile(Base):
    """One person's automation: which calendar to watch, where they live, which site to book."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    config: Mapped[dict[str, Any]]  # validated by schemas.ProfileConfig
    credentials: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted JSON
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class BookingStatus(StrEnum):
    PENDING = "pending"  # planned, trigger scheduled
    RACING = "racing"  # trigger fired, race in progress
    BOOKED = "booked"
    FAILED = "failed"
    CANCELLED = "cancelled"  # the calendar event disappeared


class Booking(Base):
    """One calendar event we are trying to book (or tried to)."""

    __tablename__ = "bookings"
    __table_args__ = (UniqueConstraint("profile_id", "event_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    event_id: Mapped[str] = mapped_column(String(1024))
    title: Mapped[str] = mapped_column(String(1024))
    play_start: Mapped[datetime]
    opens_at: Mapped[datetime]
    trigger_at: Mapped[datetime]  # opens_at - lead
    trigger_ref: Mapped[str | None] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(16), default=BookingStatus.PENDING)
    result: Mapped[dict[str, Any] | None]
    attempts: Mapped[list[Any]] = mapped_column(default=list)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class VenueCache(Base):
    """Last venue list fetched from each provider (refreshed daily or on demand)."""

    __tablename__ = "venue_cache"

    provider: Mapped[str] = mapped_column(String(64), primary_key=True)
    venues: Mapped[list[Any]]
    fetched_at: Mapped[datetime]
