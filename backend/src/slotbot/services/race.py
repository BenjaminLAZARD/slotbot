"""The booking race: wake up before the window opens, poll every second, book the best free slot."""

import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, TypeVar

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from slotbot.adapters.clock import sleep_until
from slotbot.adapters.vault import Vault
from slotbot.domain.describe import compose, notification, result_lines, retitle
from slotbot.domain.ranking import candidates
from slotbot.domain.types import Attempt, BookingResult, Outcome, Plan, RaceReport, Slot
from slotbot.models import Booking, BookingStatus, Profile, utcnow
from slotbot.ports import Calendar, Clock, EventChanges, Notifier, Provider, ProviderSession
from slotbot.providers import ProviderRegistry
from slotbot.schemas import ProfileConfig
from slotbot.services.planner import Planner
from slotbot.services.sync import SyncService

log = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class Timing:
    lead: timedelta  # how early the trigger fires (login happens then)
    poll_start: timedelta  # how long before opening we start polling
    poll_every: float  # seconds between availability polls
    retry_for: timedelta  # how long after opening we keep trying


# A free slot this close to the requested time can't be beaten by checking further venues.
IDEAL = timedelta(minutes=30)


async def run_race(plan: Plan, session: ProviderSession, clock: Clock, timing: Timing) -> RaceReport:
    """Wait for the window to open, then book the best acceptable slot, best first.

    1. Before opening: ask `is_open` once per `poll_every` (one cheap request).
    2. Once open: walk candidates in order — requested time first, then nearest times; closest
       venue first within a time — loading each venue's availability only when needed. Stops on
       the first booking, or when every acceptable slot was refused ("rejection").
    Network errors are logged once and retried until `retry_for` after opening.
    """
    if not plan.venues:
        return RaceReport(None, "", (), "no venue in bike range")
    day = plan.window.preferred.date()
    journal = _Journal(clock)

    await sleep_until(clock, plan.opens_at - timing.poll_start, chunk=timing.poll_every)
    deadline = max(plan.opens_at, clock.now()) + timing.retry_for

    while not await journal.call("opening check", session.is_open(day, plan.venues[0].venue), False):
        if clock.now() >= deadline:
            return journal.report("the booking window did not open in time")
        await clock.sleep(timing.poll_every)

    known: dict[str, list[Slot]] = {}
    refused: set[tuple[str, str, datetime]] = set()
    while clock.now() < deadline:
        slot = await _next_candidate(session, day, plan, known, refused, journal)
        if slot is None:
            if len(known) == len(plan.venues):
                reason = "every acceptable slot was taken" if refused else "no acceptable slot was free"
                return journal.report(reason)
            await clock.sleep(timing.poll_every)  # a venue failed to load; try again
            continue
        result = await journal.book(session, slot)
        if result.outcome is Outcome.BOOKED:
            return journal.report("", slot, result)
        if result.outcome is Outcome.TAKEN:
            refused.add((slot.venue.id, slot.court, slot.start))
        else:
            await clock.sleep(timing.poll_every)
    return journal.report("gave up: retry window closed")


async def _next_candidate(
    session: ProviderSession,
    day: date,
    plan: Plan,
    known: dict[str, list[Slot]],
    refused: set[tuple[str, str, datetime]],
    journal: "_Journal",
) -> Slot | None:
    """Best free slot, loading venues closest-first until no further venue could beat it."""

    def best() -> Slot | None:
        free = [s for slots in known.values() for s in slots if (s.venue.id, s.court, s.start) not in refused]
        ordered = candidates(free, plan.venues, plan.window)
        return ordered[0] if ordered else None

    for ranked in plan.venues:
        if (top := best()) and abs(top.start - plan.window.preferred) <= IDEAL:
            return top
        if ranked.venue.id not in known:
            slots = await journal.call(ranked.venue.name, session.free_slots(day, ranked.venue), None)
            if slots is None:
                return None
            known[ranked.venue.id] = slots
    return best()


class _Journal:
    """Attempts made during a race; errors are recorded once per distinct message."""

    def __init__(self, clock: Clock):
        self._clock = clock
        self.attempts: list[Attempt] = []
        self._last_error = ""

    async def call(self, what: str, step: Awaitable[T], default: T) -> T:
        try:
            return await step
        except NotImplementedError:
            raise
        except Exception as e:  # an overloaded server right at opening is normal; keep going
            if (error := f"{what}: {type(e).__name__}: {e}") != self._last_error:
                self.attempts.append(Attempt(self._clock.now(), what, None, Outcome.ERROR, error))
                self._last_error = error
            return default

    async def book(self, session: ProviderSession, slot: Slot) -> BookingResult:
        try:
            result = await session.book(slot)
        except NotImplementedError:
            raise
        except Exception as e:
            result = BookingResult(Outcome.ERROR, f"{type(e).__name__}: {e}")
        self.attempts.append(
            Attempt(self._clock.now(), slot.label, slot.start, result.outcome, result.detail)
        )
        return result

    def report(
        self, reason: str, booked: Slot | None = None, result: BookingResult | None = None
    ) -> RaceReport:
        if result is None:
            return RaceReport(booked, "", tuple(self.attempts), reason)
        return RaceReport(
            booked,
            result.reference,
            tuple(self.attempts),
            reason,
            result.detail,
            result.price,
            result.balance,
        )


class RaceService:
    """Runs one race for a booking row, records the outcome, then plans the next event."""

    def __init__(
        self,
        sessions: async_sessionmaker,
        calendar: Calendar,
        planner: Planner,
        providers: ProviderRegistry,
        vault: Vault,
        clock: Clock,
        timing: Timing,
        sync: SyncService,
        notifier: Notifier | None = None,
    ):
        self._sessions = sessions
        self._calendar = calendar
        self._planner = planner
        self._providers = providers
        self._vault = vault
        self._clock = clock
        self._timing = timing
        self._sync = sync
        self._notifier = notifier

    async def run(self, booking_id: int) -> None:
        async with self._sessions() as db:
            claimed = await db.execute(  # atomic pending -> racing: duplicate triggers are no-ops
                update(Booking)
                .where(Booking.id == booking_id, Booking.status == BookingStatus.PENDING)
                .values(status=BookingStatus.RACING, updated_at=utcnow())
            )
            await db.commit()
            if claimed.rowcount != 1:
                log.info("booking %s is not pending; skipping", booking_id)
                return
            booking = await db.get(Booking, booking_id)
            profile = await db.get(Profile, booking.profile_id)
        cfg = ProfileConfig.model_validate(profile.config)

        try:
            provider = self._providers.get(cfg.provider)
            event = await self._calendar.get(cfg.calendar_id, booking.event_id)
            if event is None:
                await self._save(booking_id, BookingStatus.CANCELLED, {"reason": "event deleted"}, ())
                return
            plan = await self._planner.plan(event, cfg, provider)
            report = await self._race(plan, provider, profile.credentials)
        except Exception as e:
            log.exception("race for booking %s failed before completing", booking_id)
            reason = f"{type(e).__name__}: {e}"
            await self._save(booking_id, BookingStatus.FAILED, {"reason": reason}, ())
            await self._notify(cfg, f"Not booked: {booking.title}", f"The bot could not race: {reason}")
            return

        await self._record(booking_id, cfg, plan, report)
        await self._notify(cfg, *notification(plan, report))
        try:
            await self._sync.sync_profile(profile.id, refresh_venues=True)  # prepare the next event
        except Exception:
            log.exception("post-race sync failed for profile %s", profile.id)

    async def _notify(self, cfg: ProfileConfig, subject: str, body: str) -> None:
        if not (self._notifier and cfg.notify_email):
            return
        try:
            await self._notifier.send(cfg.notify_email, subject, body)
        except Exception:  # a failed email must never hide the booking result
            log.exception("could not send the notification to %s", cfg.notify_email)

    async def _race(self, plan: Plan, provider: Provider, sealed: str | None) -> RaceReport:
        creds = self._vault.open(sealed) if sealed else {}
        if missing := [f for f in provider.credential_fields if not creds.get(f)]:
            return RaceReport(None, "", (), f"missing credentials: {', '.join(missing)}")
        try:
            async with provider.session(creds) as session:  # logs in now, ~lead before opening
                return await run_race(plan, session, self._clock, self._timing)
        except Exception as e:
            return RaceReport(None, "", (), f"{type(e).__name__}: {e}")

    async def _record(self, booking_id: int, cfg: ProfileConfig, plan: Plan, report: RaceReport) -> None:
        slot = report.booked
        result: dict[str, Any] = (
            {
                "venue": slot.label,
                "address": slot.venue.address,
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "reference": report.reference,
                "note": report.note,
            }
            if slot
            else {"reason": report.reason}
        )
        status = BookingStatus.BOOKED if slot else BookingStatus.FAILED
        await self._save(booking_id, status, result, report.attempts)

        t = cfg.titles
        event = plan.event
        changes = EventChanges(
            title=retitle(event.title, t.success if slot else t.failure, t.pending, t.candidate, t.failure),
            description=compose(event.description, result_lines(plan, report)),
            location=f"{slot.venue.name}, {slot.venue.address}" if slot else None,
            start=slot.start if slot else None,
            end=slot.end if slot else None,
        )
        try:
            await self._calendar.update(cfg.calendar_id, event.id, changes)
        except Exception:
            log.exception("could not write the race result to the calendar (booking %s)", booking_id)

    async def _save(
        self, booking_id: int, status: BookingStatus, result: dict[str, Any], attempts: tuple[Attempt, ...]
    ) -> None:
        rows = [
            {
                "at": a.at.isoformat(),
                "venue": a.venue,
                "start": a.start.isoformat() if a.start else None,
                "outcome": str(a.outcome),
                "detail": a.detail,
            }
            for a in attempts
        ]
        async with self._sessions() as db:
            await db.execute(
                update(Booking)
                .where(Booking.id == booking_id)
                .values(status=status, result=result, attempts=rows, updated_at=utcnow())
            )
            await db.commit()
