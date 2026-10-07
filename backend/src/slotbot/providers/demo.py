"""A fake booking system to exercise the whole flow (calendar, planning, race) without a real site.

It follows Madrid's opening rule, offers hourly slots 08:00-22:00 at three venues around Sol,
and always refuses the first booking attempt so the fallback order shows up in the log.
Nothing is ever booked; results are tagged `demo`.
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from types import TracebackType
from zoneinfo import ZoneInfo

from slotbot.domain.types import BookingResult, GeoPoint, Outcome, Slot, Venue

_VENUES = (
    Venue("demo-a", "Demo Court A (Retiro)", "Paseo de Fernán Núñez", GeoPoint(40.4123, -3.6862)),
    Venue("demo-b", "Demo Court B (Casa de Campo)", "Camino del Príncipe 2", GeoPoint(40.4214, -3.7357)),
    Venue("demo-c", "Demo Court C (Barajas)", "Avenida de Logroño 70", GeoPoint(40.4630, -3.5877)),
)


class DemoProvider:
    key = "demo"
    label = "Demo · simulated, books nothing"
    tz = ZoneInfo("Europe/Madrid")
    credential_fields: tuple[str, ...] = ()

    def opens_at(self, play_start: datetime) -> datetime:
        day = play_start.astimezone(self.tz).date() - timedelta(days=6)
        return datetime.combine(day, time(0, 0), self.tz)

    async def venues(self) -> list[Venue]:
        return list(_VENUES)

    def session(self, credentials: dict[str, str]) -> "DemoSession":
        return DemoSession(self.tz)


class DemoSession:
    def __init__(self, tz: ZoneInfo):
        self._tz = tz
        self._refused_once = False

    async def __aenter__(self) -> "DemoSession":
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    async def free_slots(self, day: date, venues: Sequence[Venue]) -> list[Slot]:
        starts = [datetime.combine(day, time(hour), self._tz) for hour in range(8, 22)]
        return [Slot(v, s, s + timedelta(hours=1), ref=f"{v.id}@{s:%H%M}") for v in venues for s in starts]

    async def book(self, slot: Slot) -> BookingResult:
        if not self._refused_once:
            self._refused_once = True
            return BookingResult(Outcome.TAKEN, "demo: someone was faster")
        return BookingResult(Outcome.BOOKED, reference=f"demo-{slot.ref}")
