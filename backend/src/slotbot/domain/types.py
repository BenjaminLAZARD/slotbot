"""Core value types shared by every layer. Pure data: no I/O, no framework imports."""

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    location: str = ""
    description: str = ""


@dataclass(frozen=True)
class Venue:
    """A bookable place (e.g. a municipal sports centre with tennis courts)."""

    id: str
    name: str
    address: str
    point: GeoPoint


@dataclass(frozen=True)
class RankedVenue:
    venue: Venue
    minutes: int  # estimated bike time from the player's origin


@dataclass(frozen=True)
class Slot:
    venue: Venue
    start: datetime
    end: datetime
    court: str = ""  # e.g. "Tenis 1" when a venue has several courts
    ref: str = ""  # opaque provider handle needed to book this exact slot

    @property
    def label(self) -> str:
        return f"{self.venue.name} · {self.court}" if self.court else self.venue.name


class Outcome(StrEnum):
    BOOKED = "booked"
    TAKEN = "taken"
    ERROR = "error"


@dataclass(frozen=True)
class BookingResult:
    outcome: Outcome
    detail: str = ""
    reference: str = ""
    price: float | None = None  # amount paid, when the provider reports it
    balance: float | None = None  # prepaid balance left afterwards, when the provider has one


@dataclass(frozen=True)
class Attempt:
    at: datetime
    venue: str
    start: datetime | None
    outcome: Outcome
    detail: str = ""


@dataclass(frozen=True)
class Constraints:
    """Limits the user wrote in the event description (`key: value` lines)."""

    earliest: time | None = None
    latest: time | None = None
    only: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    max_bike_minutes: int | None = None


@dataclass(frozen=True)
class Window:
    """Acceptable slot start times. `latest=None` means 'any later slot that day'."""

    preferred: datetime
    earliest: datetime
    latest: datetime | None


@dataclass(frozen=True)
class Plan:
    """Everything needed to race for one calendar event."""

    event: CalendarEvent
    origin: str
    venues: tuple[RankedVenue, ...]
    window: Window
    opens_at: datetime
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RaceReport:
    booked: Slot | None
    reference: str
    attempts: tuple[Attempt, ...]
    reason: str = ""
    note: str = ""  # e.g. what was paid and the remaining balance
    price: float | None = None
    balance: float | None = None

    @property
    def balance_low(self) -> bool:
        """The balance left would not pay for the same booking again."""
        return self.balance is not None and self.price is not None and self.balance < self.price
