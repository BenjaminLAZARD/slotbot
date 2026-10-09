"""Sync + race end to end, with the demo provider and in-memory fakes for Google and geocoding."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet
from sqlalchemy import select

from slotbot.adapters.vault import Vault
from slotbot.domain.describe import MARKER
from slotbot.domain.types import CalendarEvent
from slotbot.models import Booking, Profile
from slotbot.providers import ProviderRegistry
from slotbot.providers.demo import DemoProvider
from slotbot.schemas import ProfileConfig
from slotbot.services.planner import Planner
from slotbot.services.race import RaceService, Timing
from slotbot.services.sync import SyncService
from slotbot.services.venues import VenueCatalogue
from tests.conftest import FakeCalendar, FakeGeocoder, FakeTriggers

MAD = ZoneInfo("Europe/Madrid")
TIMING = Timing(timedelta(minutes=5), timedelta(seconds=60), 1.0, timedelta(seconds=30))


def event(eid: str, title: str, day: int, hour: int = 19, description: str = "") -> CalendarEvent:
    start = datetime(2026, 10, day, hour, tzinfo=MAD)
    return CalendarEvent(eid, title, start, start + timedelta(hours=1), "Sol, Madrid", description)


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


class ImmediateTriggers(FakeTriggers):
    """Fires the race inside schedule(), like a trigger that is already due (local timers, Cloud Tasks)."""

    fire = None

    async def schedule(self, booking_id: int, at: datetime) -> str:
        ref = await super().schedule(booking_id, at)
        await self.fire(booking_id)
        return ref


async def build(sessions, clock, events, notifier: FakeNotifier | None = None, triggers=None):
    calendar, triggers = FakeCalendar(events), triggers or FakeTriggers()
    providers = ProviderRegistry([DemoProvider()])
    planner = Planner(FakeGeocoder(), VenueCatalogue(sessions, clock))
    sync = SyncService(sessions, calendar, planner, providers, triggers, clock, TIMING.lead)
    vault = Vault(Fernet.generate_key().decode())
    race = RaceService(sessions, calendar, planner, providers, vault, clock, TIMING, sync, notifier)
    async with sessions() as db:
        cfg = ProfileConfig(calendar_id="cal", provider="demo", notify_email="me@example.com")
        profile = Profile(name="me", config=cfg.model_dump())
        db.add(profile)
        await db.commit()
    return calendar, triggers, sync, race, profile.id


async def test_sync_marks_next_candidate_pending_and_schedules_trigger(sessions, clock):
    events = [
        event("past", "Success - Tennis", 1),
        event("e1", "Candidate Tennis w/ Ana", 13, description="latest: 21:00"),
        event("e2", "Candidate Tennis", 15),
    ]
    calendar, triggers, sync, _, pid = await build(sessions, clock, events)

    booking = await sync.sync_profile(pid)

    assert booking.event_id == "e1"
    e1 = calendar.events["e1"]
    assert e1.title == "Pending Tennis w/ Ana"
    assert e1.description.startswith(f"latest: 21:00\n\n{MARKER}\nStatus: pending")
    assert "accepts 19:00 → 21:00" in e1.description
    assert "1. Demo Court A (Retiro)" in e1.description
    assert calendar.events["e2"].title == "Candidate Tennis"  # only the next one
    opens = datetime(2026, 10, 7, 0, 0, tzinfo=MAD)
    assert list(triggers.scheduled.values()) == [(booking.id, opens - TIMING.lead)]

    await sync.sync_profile(pid)  # idempotent: same trigger, no duplicate
    assert len(triggers.scheduled) == 1


async def test_race_books_writes_back_and_promotes_next_event(sessions, clock):
    events = [event("e1", "Candidate Tennis", 13), event("e2", "Candidate Tennis", 15)]
    notifier = FakeNotifier()
    calendar, triggers, sync, race, pid = await build(sessions, clock, events, notifier)
    booking = await sync.sync_profile(pid)
    clock.current = booking.trigger_at

    await race.run(booking.id)

    [(to, subject, body)] = notifier.sent
    assert to == "me@example.com"
    assert subject == "Booked: Demo Court B (Casa de Campo) · Court 1, Tue 13 Oct 19:00"
    assert "taken" in body  # the attempts are in the email too
    e1 = calendar.events["e1"]
    assert e1.title == "Success - Tennis"
    assert e1.start.hour == 19 and e1.location.startswith("Demo Court B")  # A refused once by demo
    assert "Result: BOOKED Demo Court B (Casa de Campo)" in e1.description
    assert "Demo Court A (Retiro) · Court 1 19:00 → taken" in e1.description
    assert calendar.events["e2"].title == "Pending Tennis"  # next one prepared right away
    async with sessions() as db:
        statuses = {b.event_id: b.status for b in await db.scalars(select(Booking))}
    assert statuses == {"e1": "booked", "e2": "pending"}

    await race.run(booking.id)  # a duplicate trigger is a no-op
    assert calendar.events["e1"].title == "Success - Tennis"


async def test_a_trigger_due_now_sees_the_saved_booking(sessions, clock):
    # 2 days ahead: the booking window is already open, so the trigger fires as soon as it's scheduled.
    triggers = ImmediateTriggers()
    calendar, _, sync, race, pid = await build(
        sessions, clock, [event("e1", "Candidate Tennis", 7)], triggers=triggers
    )
    triggers.fire = race.run

    await sync.sync_profile(pid)

    assert (
        calendar.events["e1"].title == "Success - Tennis"
    )  # the race ran instead of "not pending; skipping"


async def test_race_marks_cancelled_when_event_was_deleted(sessions, clock):
    calendar, _, sync, race, pid = await build(sessions, clock, [event("e1", "Candidate Tennis", 13)])
    booking = await sync.sync_profile(pid)
    del calendar.events["e1"]

    await race.run(booking.id)

    async with sessions() as db:
        assert (await db.get(Booking, booking.id)).status == "cancelled"


async def agenda_for(sessions, clock, calendar, triggers, sync):
    from slotbot.services.agenda import AgendaService

    vault = Vault(Fernet.generate_key().decode())
    providers = ProviderRegistry([DemoProvider()])
    return AgendaService(sessions, calendar, providers, vault, triggers, clock, sync, next_sync=lambda: None)


async def test_agenda_lists_stages_wake_time_and_allowed_actions(sessions, clock):
    events = [
        event("e1", "Candidate Tennis", 13),
        event("e2", "Candidate Tennis", 15),
        event("e3", "Dentist", 14),
    ]
    calendar, triggers, sync, race, pid = await build(sessions, clock, events)
    booking = await sync.sync_profile(pid)
    agenda = await (await agenda_for(sessions, clock, calendar, triggers, sync)).agenda(pid)

    stages = {i.event.id: (i.stage, i.actions) for i in agenda.items}
    assert stages == {  # "Dentist" is not the bot's business: left out
        "e1": ("pending", ("cancel", "reset")),
        "e2": ("candidate", ("cancel",)),
    }
    assert agenda.next_wake.event.id == "e1" and agenda.next_wake.wakes_at == booking.trigger_at


async def test_cancel_a_booked_event_cancels_on_the_site_then_reset_makes_it_a_candidate(sessions, clock):
    from slotbot.services.agenda import ActionRefused

    events = [event("e1", "Candidate Tennis", 13), event("e2", "Candidate Tennis", 15)]
    calendar, triggers, sync, race, pid = await build(sessions, clock, events)
    booking = await sync.sync_profile(pid)
    clock.current = booking.trigger_at
    await race.run(booking.id)  # demo books e1
    service = await agenda_for(sessions, clock, calendar, triggers, sync)

    try:
        await service.reset(pid, "e1")
        raise AssertionError("reset of a paid booking must be refused")
    except ActionRefused:
        pass

    detail = await service.cancel(pid, "e1")
    assert detail.startswith("demo:") and calendar.events["e1"].title == "Cancelled - Tennis"
    async with sessions() as db:
        assert (await db.get(Booking, booking.id)).status == "cancelled"

    await service.reset(pid, "e1")
    # e1 is a candidate again and, being the earliest, becomes the pending one once more
    assert calendar.events["e1"].title == "Pending Tennis"


async def test_budget_notification_cuts_billing_only_at_the_cap():
    import base64
    import json

    from fastapi.testclient import TestClient

    from slotbot.api import jobs
    from slotbot.api.deps import get_container

    class Switch:
        calls = 0

        async def disable_billing(self) -> None:
            Switch.calls += 1

    class Settings:
        job_token = "s3cret"
        job_caller = ""

    class Container:
        settings = Settings()
        kill_switch = Switch()

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(jobs.router)
    app.dependency_overrides[get_container] = lambda: Container()
    client = TestClient(app)

    def push(cost: float) -> dict:
        data = base64.b64encode(json.dumps({"costAmount": cost, "budgetAmount": 10.0}).encode()).decode()
        return {"message": {"data": data}, "subscription": "projects/p/subscriptions/s"}

    assert client.post("/jobs/budget", json=push(12.0)).status_code == 403  # no token
    assert client.post("/jobs/budget?token=s3cret", json=push(5.0)).json() == {"billing_disabled": False}
    assert client.post("/jobs/budget?token=s3cret", json=push(10.0)).json() == {"billing_disabled": True}
    assert Switch.calls == 1
