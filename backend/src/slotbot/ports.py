"""Interfaces the services depend on. Adapters (Google, Madrid, Cloud Tasks...) implement them."""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from slotbot.domain.types import BookingResult, CalendarEvent, GeoPoint, Slot, Venue


@dataclass(frozen=True)
class EventChanges:
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start: datetime | None = None
    end: datetime | None = None


class Calendar(Protocol):
    async def upcoming(self, calendar_id: str, start: datetime, days: int) -> list[CalendarEvent]: ...

    async def get(self, calendar_id: str, event_id: str) -> CalendarEvent | None: ...

    async def update(self, calendar_id: str, event_id: str, changes: EventChanges) -> None: ...


class Geocoder(Protocol):
    async def locate(self, query: str) -> GeoPoint | None: ...


class ProviderSession(Protocol):
    """A logged-in session with a booking system, alive for one race."""

    async def free_slots(self, day: date, venues: Sequence[Venue]) -> list[Slot]:
        """Slots bookable right now. Empty before the booking window opens."""
        ...

    async def book(self, slot: Slot) -> BookingResult: ...


class Provider(Protocol):
    """A booking system (Madrid municipal tennis, Paris Tennis, ...)."""

    key: str
    label: str
    tz: ZoneInfo
    credential_fields: tuple[str, ...]

    def opens_at(self, play_start: datetime) -> datetime:
        """When slots starting at `play_start` become bookable."""
        ...

    async def venues(self) -> list[Venue]: ...

    def session(self, credentials: dict[str, str]) -> AbstractAsyncContextManager[ProviderSession]: ...


class Triggers(Protocol):
    """Calls POST /jobs/race/{booking_id} at a given time (Cloud Tasks in prod, a loop locally)."""

    async def schedule(self, booking_id: int, at: datetime) -> str:
        """Return an opaque reference that `cancel` understands."""
        ...

    async def cancel(self, ref: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...

    async def sleep(self, seconds: float) -> None: ...
