from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from slotbot.domain.constraints import Constraints
from slotbot.domain.ranking import window
from slotbot.domain.types import (
    BookingResult,
    CalendarEvent,
    GeoPoint,
    Outcome,
    Plan,
    RankedVenue,
    Slot,
    Venue,
)
from slotbot.services.race import Timing, run_race

MAD = ZoneInfo("Europe/Madrid")
A = Venue("a", "Court A", "", GeoPoint(0, 0))
B = Venue("b", "Court B", "", GeoPoint(0, 0))
OPENS = datetime(2026, 10, 7, 0, 0, tzinfo=MAD)
PLAY = datetime(2026, 10, 13, 19, 0, tzinfo=MAD)
TIMING = Timing(timedelta(minutes=5), timedelta(seconds=60), 1.0, timedelta(seconds=120))


class Session:
    """Closed until OPENS; then offers 19:00 and 20:00 at both courts; refuses `taken`."""

    def __init__(self, clock, taken: set[tuple[str, int]]):
        self.clock, self.taken, self.polls = clock, taken, 0

    async def free_slots(self, day: date, venues: Sequence[Venue]) -> list[Slot]:
        self.polls += 1
        if self.clock.now() < OPENS:
            return []
        hours = (19, 20)
        return [Slot(v, PLAY.replace(hour=h), PLAY.replace(hour=h + 1)) for v in venues for h in hours]

    async def book(self, slot: Slot) -> BookingResult:
        if (slot.venue.id, slot.start.hour) in self.taken:
            return BookingResult(Outcome.TAKEN, "already reserved")
        return BookingResult(Outcome.BOOKED, reference="R1")


def plan() -> Plan:
    event = CalendarEvent("e1", "Pending Tennis", PLAY, PLAY + timedelta(hours=1))
    return Plan(
        event=event,
        origin="Sol",
        venues=(RankedVenue(A, 5), RankedVenue(B, 10)),
        window=window(PLAY, 0, None, Constraints()),
        opens_at=OPENS,
    )


async def test_polls_until_open_then_falls_back_court_then_time(clock):
    clock.current = OPENS - timedelta(minutes=5)  # trigger fires at opens - lead
    session = Session(clock, taken={("a", 19), ("b", 19)})

    report = await run_race(plan(), session, clock, TIMING)

    assert report.booked and (report.booked.venue.id, report.booked.start.hour) == ("a", 20)
    assert [(a.venue, a.outcome) for a in report.attempts] == [
        ("Court A", Outcome.TAKEN),
        ("Court B", Outcome.TAKEN),
        ("Court A", Outcome.BOOKED),
    ]
    assert session.polls == 61  # once a second from opens-60s, booked on the first open poll


async def test_gives_up_after_retry_window_without_retrying_refused_slots(clock):
    clock.current = OPENS
    session = Session(clock, taken={("a", 19), ("b", 19), ("a", 20), ("b", 20)})

    report = await run_race(plan(), session, clock, TIMING)

    assert report.booked is None
    assert report.reason == "every acceptable slot was taken"
    assert len(report.attempts) == 4  # each refused slot tried once
    assert clock.now() >= OPENS + TIMING.retry_for
