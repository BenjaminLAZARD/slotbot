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
    """Opens at OPENS (or never); offers 19:00 and 20:00 at every venue; refuses `taken`."""

    def __init__(self, clock, taken: set[tuple[str, int]], opens: datetime | None = OPENS):
        self.clock, self.taken, self.opens = clock, taken, opens
        self.open_checks = 0
        self.loaded: list[str] = []

    async def is_open(self, day: date, venue: Venue) -> bool:
        self.open_checks += 1
        return self.opens is not None and self.clock.now() >= self.opens

    async def free_slots(self, day: date, venue: Venue) -> list[Slot]:
        self.loaded.append(venue.id)
        return [Slot(venue, PLAY.replace(hour=h), PLAY.replace(hour=h + 1)) for h in (19, 20)]

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


async def test_waits_for_opening_then_tries_other_court_before_other_time(clock):
    clock.current = OPENS - timedelta(minutes=5)  # trigger fires at opens - lead
    session = Session(clock, taken={("a", 19), ("b", 19)})

    report = await run_race(plan(), session, clock, TIMING)

    assert report.booked and (report.booked.venue.id, report.booked.start.hour) == ("a", 20)
    assert [(a.venue, a.start.hour, a.outcome) for a in report.attempts] == [
        ("Court A", 19, Outcome.TAKEN),
        ("Court B", 19, Outcome.TAKEN),
        ("Court A", 20, Outcome.BOOKED),
    ]
    assert session.open_checks == 61  # once a second from opens-60s, open on the 61st check


async def test_closest_venue_with_requested_time_is_booked_without_loading_others(clock):
    clock.current = OPENS
    session = Session(clock, taken=set())

    report = await run_race(plan(), session, clock, TIMING)

    assert report.booked and report.booked.venue.id == "a"
    assert session.loaded == ["a"]  # one grid fetched: speed matters at opening


async def test_stops_on_rejection_without_retrying_refused_slots(clock):
    clock.current = OPENS
    session = Session(clock, taken={("a", 19), ("b", 19), ("a", 20), ("b", 20)})

    report = await run_race(plan(), session, clock, TIMING)

    assert report.booked is None
    assert report.reason == "every acceptable slot was taken"
    assert len(report.attempts) == 4  # each slot tried once
    assert clock.now() == OPENS  # a rejection ends the race at once


async def test_an_account_problem_stops_the_race_at_once(clock):
    from slotbot.errors import AbortRace

    class SignedOut(Session):
        async def book(self, slot: Slot) -> BookingResult:
            raise AbortRace("the site refused the account: Para acceder ... es necesario identificarse")

    clock.current = OPENS
    report = await run_race(plan(), SignedOut(clock, taken=set()), clock, TIMING)

    assert report.booked is None
    assert report.reason.startswith("stopped: the site refused the account")
    assert len(report.attempts) == 1  # no burst of retries on other courts/times


async def test_gives_up_if_the_window_never_opens(clock):
    clock.current = OPENS
    report = await run_race(plan(), Session(clock, taken=set(), opens=None), clock, TIMING)

    assert report.booked is None
    assert report.reason == "the booking window did not open in time"
    assert clock.now() >= OPENS + TIMING.retry_for
