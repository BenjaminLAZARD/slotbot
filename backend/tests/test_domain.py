from datetime import datetime, time
from zoneinfo import ZoneInfo

from slotbot.domain.constraints import parse_constraints
from slotbot.domain.describe import MARKER, compose, retitle, user_part
from slotbot.domain.ranking import candidates, nearby, window
from slotbot.domain.types import Constraints, GeoPoint, RankedVenue, Slot, Venue

MAD = ZoneInfo("Europe/Madrid")
SOL = GeoPoint(40.4168, -3.7038)
NEAR = Venue("near", "CDM La Chopera", "", GeoPoint(40.4123, -3.6862))  # ~3 km
FAR = Venue("far", "CDM Chamartín", "", GeoPoint(40.4630, -3.6800))  # ~6 km
OUT = Venue("out", "CDM Barajas", "", GeoPoint(40.4630, -3.5877))  # ~11 km


def at(hour: int, day: int = 13) -> datetime:
    return datetime(2026, 10, day, hour, 0, tzinfo=MAD)


def test_constraints_read_keys_and_warn_on_garbage():
    c, warnings = parse_constraints("Bring balls\nlatest: 21h\nAvoid: Casa de Campo, Gallur\nearliest: 9pm")
    assert c.latest == time(21, 0)
    assert c.avoid == ("Casa de Campo", "Gallur")
    assert c.earliest is None
    assert warnings == ("ignored 'earliest: 9pm' (expected a time like 21:00)",)


def test_constraints_read_html_descriptions():
    c, _ = parse_constraints("only: Chopera<br>max_bike: 20&nbsp;")
    assert c.only == ("Chopera",)
    assert c.max_bike_minutes == 20


def test_nearby_sorts_by_bike_time_and_applies_only_avoid():
    ranked = nearby([FAR, OUT, NEAR], SOL, max_minutes=30)
    assert [r.venue.id for r in ranked] == ["near", "far"]
    ranked = nearby([FAR, NEAR], SOL, 30, Constraints(avoid=("chopera",)))  # accent/case-insensitive
    assert [r.venue.id for r in ranked] == ["far"]


def test_window_weekday_is_open_ended_and_constraints_override():
    w = window(at(19), before_minutes=0, after_minutes=None, constraints=Constraints())
    assert (w.earliest, w.latest) == (at(19), None)
    w = window(at(19), 0, None, Constraints(earliest=time(18), latest=time(21)))
    assert (w.earliest, w.latest) == (at(18), at(21))


def test_candidates_try_requested_time_first_then_closest_venue_then_later_times():
    venues = (RankedVenue(NEAR, 12), RankedVenue(FAR, 20))
    w = window(at(11, day=17), before_minutes=120, after_minutes=120, constraints=Constraints())
    free = [Slot(v, at(h, day=17), at(h + 1, day=17)) for v in (FAR, NEAR) for h in (8, 10, 11, 12, 14)]
    order = [(s.start.hour, s.venue.id) for s in candidates(free, venues, w)]
    assert order == [
        (11, "near"),
        (11, "far"),
        (12, "near"),
        (12, "far"),  # +1h beats -1h on a tie
        (10, "near"),
        (10, "far"),
    ]  # 08:00 and 14:00 fall outside ±2h


def test_compose_keeps_user_text_and_replaces_bot_section():
    first = compose("latest: 21:00", ["Status: pending"])
    second = compose(first, ["Status: booked"])
    assert user_part(second) == "latest: 21:00"
    assert second.endswith(f"{MARKER}\nStatus: booked")
    assert "<br>" in compose("<b>latest</b>: 21:00", ["x"])


def test_notification_flags_a_wallet_that_cannot_pay_the_next_booking():
    from slotbot.domain.describe import notification
    from slotbot.domain.types import CalendarEvent, Plan, RaceReport

    start = at(19)
    plan = Plan(
        CalendarEvent("e", "Candidate Tennis", start, at(20)),
        "Sol",
        (RankedVenue(NEAR, 8),),
        window(start, 0, None, Constraints()),
        at(0, day=7),
    )
    slot = Slot(NEAR, start, at(20), court="Tenis 2")
    subject, body = notification(plan, RaceReport(slot, "8126131707", (), price=6.9, balance=3.1))
    assert subject == "Booked: CDM La Chopera · Tenis 2, Tue 13 Oct 19:00 · top up your wallet"
    assert body.startswith("⚠ Balance left (3.10 €) is below the price just paid (6.90 €)")
    subject, _ = notification(plan, RaceReport(None, "", (), "every acceptable slot was taken"))
    assert subject == "Not booked: Candidate Tennis, Tue 13 Oct 19:00"


def test_retitle_keeps_the_rest_of_the_title():
    assert retitle("Candidate Tennis w/ Ana", "Pending Tennis", "candidate tennis") == "Pending Tennis w/ Ana"
    assert (
        retitle("Tennis w/ Ana", "Candidate Tennis", "Pending Tennis") == "Candidate Tennis · Tennis w/ Ana"
    )
