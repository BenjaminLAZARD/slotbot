"""Daily (and on-demand) pass over a profile's calendar.

Finds the next event marked as a candidate, plans it (origin, venues in bike range, acceptable
times, opening time), renames it to the pending title, writes the plan into its description and
makes sure exactly one trigger is scheduled for `opens_at - lead`.
"""

import logging
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slotbot.domain.describe import compose, has_marker, plan_lines, retitle
from slotbot.domain.types import CalendarEvent, Plan
from slotbot.errors import ConfigError
from slotbot.models import Booking, BookingStatus, Profile
from slotbot.ports import Calendar, Clock, EventChanges, Triggers
from slotbot.providers import ProviderRegistry
from slotbot.schemas import ProfileConfig, Titles
from slotbot.services.planner import Planner

log = logging.getLogger(__name__)
STALE_RACE = timedelta(minutes=45)  # a race never lasts this long; the process must have died


class SyncService:
    def __init__(
        self,
        sessions: async_sessionmaker,
        calendar: Calendar,
        planner: Planner,
        providers: ProviderRegistry,
        triggers: Triggers,
        clock: Clock,
        lead: timedelta,
    ):
        self._sessions = sessions
        self._calendar = calendar
        self._planner = planner
        self._providers = providers
        self._triggers = triggers
        self._clock = clock
        self._lead = lead

    async def sync_all(self) -> None:
        async with self._sessions() as db:
            ids = (await db.scalars(select(Profile.id))).all()
        for profile_id in ids:
            try:
                await self.sync_profile(profile_id)
            except ConfigError as e:  # setup not finished yet: one line, not a stack trace
                log.warning("sync skipped for profile %s: %s", profile_id, e)
            except Exception:
                log.exception("sync failed for profile %s", profile_id)

    async def sync_profile(self, profile_id: int, refresh_venues: bool = False) -> Booking | None:
        async with self._sessions() as db:
            profile = await db.get(Profile, profile_id)
            if profile is None:
                raise LookupError(f"profile {profile_id} not found")
            cfg = ProfileConfig.model_validate(profile.config)
            provider = self._providers.get(cfg.provider)
            await self._expire_stale_races(db, profile_id)

            events = await self._calendar.upcoming(cfg.calendar_id, self._clock.now(), cfg.lookahead_days)
            target = await self._next_target(db, profile_id, events, cfg.titles)
            if target is None:
                await db.commit()
                return None
            plan = await self._planner.plan(target, cfg, provider, refresh_venues)
            title = retitle(target.title, cfg.titles.pending, cfg.titles.candidate, cfg.titles.pending)
            booking, rearm = await self._arm(db, profile_id, plan, title)
            await db.commit()

            description = compose(target.description, plan_lines(plan, "pending"))
            if (title, description) != (target.title, target.description):
                await self._calendar.update(
                    cfg.calendar_id, target.id, EventChanges(title=title, description=description)
                )
            # Last: a trigger that is already due may run the race right away, and the race must
            # find the booking saved and write its result over "Pending", not the other way round.
            if rearm:
                at = max(booking.trigger_at, self._clock.now())
                booking.trigger_ref = await self._triggers.schedule(booking.id, at)
                await db.commit()
        return booking

    async def _next_target(
        self, db: AsyncSession, profile_id: int, events: Sequence[CalendarEvent], titles: Titles
    ) -> CalendarEvent | None:
        """Earliest event marked candidate/pending that we have not already raced for."""
        marked = [
            e for e in events if has_marker(e.title, titles.pending) or has_marker(e.title, titles.candidate)
        ]
        if not marked:
            return None
        done = set(
            await db.scalars(
                select(Booking.event_id).where(
                    Booking.profile_id == profile_id,
                    Booking.event_id.in_([e.id for e in marked]),
                    Booking.status != BookingStatus.PENDING,
                )
            )
        )
        return next((e for e in marked if e.id not in done), None)

    async def _arm(self, db: AsyncSession, profile_id: int, plan: Plan, title: str) -> tuple[Booking, bool]:
        """Upsert the booking row; True when its trigger must be (re)scheduled (after commit)."""
        desired = plan.opens_at - self._lead
        booking = await db.scalar(
            select(Booking).where(Booking.profile_id == profile_id, Booking.event_id == plan.event.id)
        )
        if booking is None:
            booking = Booking(profile_id=profile_id, event_id=plan.event.id, attempts=[])
            db.add(booking)
        booking.title = title
        booking.play_start = plan.event.start
        booking.opens_at = plan.opens_at
        if booking.trigger_ref and booking.trigger_at == desired:
            return booking, False
        if booking.trigger_ref:
            await self._triggers.cancel(booking.trigger_ref)
        booking.trigger_at = desired
        booking.trigger_ref = None
        booking.status = BookingStatus.PENDING
        return booking, True

    async def _expire_stale_races(self, db: AsyncSession, profile_id: int) -> None:
        await db.execute(
            update(Booking)
            .where(
                Booking.profile_id == profile_id,
                Booking.status == BookingStatus.RACING,
                Booking.updated_at < self._clock.now() - STALE_RACE,
            )
            .values(
                status=BookingStatus.FAILED,
                result={"reason": "interrupted mid-race; check the booking site"},
            )
        )
