"""The booking race: wake up before the window opens, poll every second, book the best free slot."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker

from slotbot.adapters.clock import sleep_until
from slotbot.adapters.vault import Vault
from slotbot.domain.describe import compose, result_lines, retitle
from slotbot.domain.ranking import candidates
from slotbot.domain.types import Attempt, BookingResult, Outcome, Plan, RaceReport
from slotbot.models import Booking, BookingStatus, Profile, utcnow
from slotbot.ports import Calendar, Clock, EventChanges, Provider, ProviderSession
from slotbot.providers import ProviderRegistry
from slotbot.schemas import ProfileConfig
from slotbot.services.planner import Planner
from slotbot.services.sync import SyncService

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Timing:
    lead: timedelta  # how early the trigger fires (login happens then)
    poll_start: timedelta  # how long before opening we start polling
    poll_every: float  # seconds between availability polls
    retry_for: timedelta  # how long after opening we keep trying


async def run_race(plan: Plan, session: ProviderSession, clock: Clock, timing: Timing) -> RaceReport:
    """Poll availability until a slot is booked or the retry window closes.

    Each pass tries every acceptable free slot in order (requested time first, then nearest
    times; closest venue first within a time). A slot refused once is not retried.
    """
    venues = [r.venue for r in plan.venues]
    if not venues:
        return RaceReport(None, "", (), "no venue in bike range")

    await sleep_until(clock, plan.opens_at - timing.poll_start, chunk=timing.poll_every)
    deadline = max(plan.opens_at, clock.now()) + timing.retry_for
    attempts: list[Attempt] = []
    refused: set[tuple[str, datetime]] = set()
    last_error = ""

    while True:
        try:
            free = await session.free_slots(plan.window.preferred.date(), venues)
        except Exception as e:  # overloaded server right at opening is normal; keep polling
            free = []
            if (error := f"{type(e).__name__}: {e}") != last_error:
                attempts.append(Attempt(clock.now(), "availability", None, Outcome.ERROR, error))
                last_error = error

        for slot in candidates(free, plan.venues, plan.window):
            if (slot.venue.id, slot.start) in refused:
                continue
            try:
                result = await session.book(slot)
            except Exception as e:
                result = BookingResult(Outcome.ERROR, f"{type(e).__name__}: {e}")
            attempts.append(Attempt(clock.now(), slot.venue.name, slot.start, result.outcome, result.detail))
            if result.outcome is Outcome.BOOKED:
                return RaceReport(slot, result.reference, tuple(attempts))
            if result.outcome is Outcome.TAKEN:
                refused.add((slot.venue.id, slot.start))

        if clock.now() >= deadline:
            reason = "every acceptable slot was taken" if refused else "no acceptable slot was offered"
            return RaceReport(None, "", tuple(attempts), reason)
        await clock.sleep(timing.poll_every)


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
    ):
        self._sessions = sessions
        self._calendar = calendar
        self._planner = planner
        self._providers = providers
        self._vault = vault
        self._clock = clock
        self._timing = timing
        self._sync = sync

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
            await self._save(booking_id, BookingStatus.FAILED, {"reason": f"{type(e).__name__}: {e}"}, ())
            return

        await self._record(booking_id, cfg, plan, report)
        try:
            await self._sync.sync_profile(profile.id, refresh_venues=True)  # prepare the next event
        except Exception:
            log.exception("post-race sync failed for profile %s", profile.id)

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
                "venue": slot.venue.name,
                "address": slot.venue.address,
                "start": slot.start.isoformat(),
                "end": slot.end.isoformat(),
                "reference": report.reference,
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
