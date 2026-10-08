"""What's coming up in a profile's calendar, and the manual actions on it (cancel, reset)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from slotbot.adapters.vault import Vault
from slotbot.domain.describe import compose, retitle, stage_of, user_part
from slotbot.domain.types import CalendarEvent
from slotbot.models import Booking, BookingStatus, Profile
from slotbot.ports import Calendar, Clock, EventChanges, Provider, Triggers
from slotbot.providers import ProviderRegistry
from slotbot.schemas import ProfileConfig
from slotbot.services.sync import SyncService

MAX_EVENTS = 10


class ActionRefused(Exception):
    """The action does not apply to this event in its current state."""


@dataclass(frozen=True)
class AgendaItem:
    event: CalendarEvent
    stage: str  # candidate | pending | racing | booked | failed | cancelled | other
    booking_id: int | None
    opens_at: datetime | None
    wakes_at: datetime | None
    court: str | None
    actions: tuple[str, ...]


@dataclass(frozen=True)
class Agenda:
    items: tuple[AgendaItem, ...]
    next_wake: AgendaItem | None
    next_sync: datetime | None


_ACTIONS = {
    "candidate": ("cancel",),
    "pending": ("cancel", "reset"),
    "racing": (),
    "booked": ("cancel",),
    "failed": ("retry", "reset", "cancel"),
    "cancelled": ("reset",),
}


class AgendaService:
    def __init__(
        self,
        sessions: async_sessionmaker,
        calendar: Calendar,
        providers: ProviderRegistry,
        vault: Vault,
        triggers: Triggers,
        clock: Clock,
        sync: SyncService,
        next_sync: Callable[[], datetime | None],
    ):
        self._sessions = sessions
        self._calendar = calendar
        self._providers = providers
        self._vault = vault
        self._triggers = triggers
        self._clock = clock
        self._sync = sync
        self._next_sync = next_sync

    async def agenda(self, profile_id: int) -> Agenda:
        """The next MAX_EVENTS events the bot deals with (candidates and what became of them)."""
        cfg, provider = await self._profile(profile_id)
        now = self._clock.now()
        events = await self._calendar.upcoming(cfg.calendar_id, now, cfg.lookahead_days)
        async with self._sessions() as db:
            rows = {
                b.event_id: b
                for b in await db.scalars(
                    select(Booking).where(
                        Booking.profile_id == profile_id, Booking.event_id.in_([e.id for e in events])
                    )
                )
            }
        markers = dict(
            zip(("candidate", "pending", "booked", "failed", "cancelled"), cfg.titles.all(), strict=True)
        )
        items = []
        for e in events:
            row = rows.get(e.id)
            stage = row.status if row else (stage_of(e.title, markers) or "other")
            if stage == "other":  # the rest of the calendar is none of the bot's business
                continue
            if len(items) == MAX_EVENTS:
                break
            if stage == "pending" and row is None:
                stage = "candidate"  # titled pending but not planned yet: the next sync picks it up
            court = (row.result or {}).get("venue") if row and row.status == BookingStatus.BOOKED else None
            items.append(
                AgendaItem(
                    event=e,
                    stage=stage,
                    booking_id=row.id if row else None,
                    opens_at=row.opens_at if row else provider.opens_at(e.start),
                    wakes_at=row.trigger_at if row and row.status == BookingStatus.PENDING else None,
                    court=court,
                    actions=_ACTIONS.get(stage, ()),
                )
            )
        waiting = [i for i in items if i.wakes_at]
        next_wake = min(waiting, key=lambda i: i.wakes_at) if waiting else None
        return Agenda(tuple(items), next_wake, self._next_sync())

    async def cancel(self, profile_id: int, event_id: str) -> str:
        """Stop the bot for this event; if it is already booked, cancel on the booking site too."""
        cfg, provider = await self._profile(profile_id)
        event = await self._event(cfg, event_id)
        detail = "the bot will not book it"
        async with self._sessions() as db:
            row = await self._row(db, profile_id, event_id)
            if row and row.status == BookingStatus.RACING:
                raise ActionRefused("a race is running for this event; try again in a few minutes")
            if row and row.status == BookingStatus.BOOKED:
                detail = await self._cancel_on_site(
                    provider, profile_id, (row.result or {}).get("reference", "")
                )
            if row is None:
                row = Booking(
                    profile_id=profile_id,
                    event_id=event_id,
                    play_start=event.start,
                    opens_at=provider.opens_at(event.start),
                    trigger_at=provider.opens_at(event.start),
                    attempts=[],
                )
                db.add(row)
            if row.trigger_ref:
                await self._triggers.cancel(row.trigger_ref)
            title = retitle(event.title, cfg.titles.cancelled, *cfg.titles.all())
            row.status, row.trigger_ref, row.title = BookingStatus.CANCELLED, None, title
            row.result = {**(row.result or {}), "cancelled": detail}
            await db.commit()
        when = f"{self._clock.now().astimezone(provider.tz):%a %d %b %H:%M}"
        lines = [f"Status: cancelled · {when}", detail]
        await self._calendar.update(
            cfg.calendar_id,
            event_id,
            EventChanges(title=title, description=compose(event.description, lines)),
        )
        await self._sync.sync_profile(profile_id)  # promote the next candidate if this one was next
        return detail

    async def reset(self, profile_id: int, event_id: str) -> None:
        """Make the event a fresh candidate again (forgetting past attempts) and re-plan."""
        cfg, _ = await self._profile(profile_id)
        event = await self._event(cfg, event_id)
        async with self._sessions() as db:
            row = await self._row(db, profile_id, event_id)
            if row and row.status == BookingStatus.BOOKED:
                raise ActionRefused("this event is booked and paid: cancel it first, then reset")
            if row and row.status == BookingStatus.RACING:
                raise ActionRefused("a race is running for this event; try again in a few minutes")
            if row:
                if row.trigger_ref:
                    await self._triggers.cancel(row.trigger_ref)
                await db.delete(row)
                await db.commit()
        title = retitle(event.title, cfg.titles.candidate, *cfg.titles.all())
        await self._calendar.update(
            cfg.calendar_id, event_id, EventChanges(title=title, description=user_part(event.description))
        )
        await self._sync.sync_profile(profile_id)

    async def _cancel_on_site(self, provider: Provider, profile_id: int, reference: str) -> str:
        if not reference:
            raise ActionRefused("no booking reference stored: cancel it on the booking site")
        async with self._sessions() as db:
            sealed = (await db.get(Profile, profile_id)).credentials
        creds = self._vault.open(sealed) if sealed else {}
        async with provider.session(creds) as session:
            return await session.cancel(reference)

    async def _profile(self, profile_id: int) -> tuple[ProfileConfig, Provider]:
        async with self._sessions() as db:
            profile = await db.get(Profile, profile_id)
        if profile is None:
            raise LookupError(f"profile {profile_id} not found")
        cfg = ProfileConfig.model_validate(profile.config)
        return cfg, self._providers.get(cfg.provider)

    async def _event(self, cfg: ProfileConfig, event_id: str) -> CalendarEvent:
        if (event := await self._calendar.get(cfg.calendar_id, event_id)) is None:
            raise LookupError("event not found in the calendar")
        return event

    @staticmethod
    async def _row(db: AsyncSession, profile_id: int, event_id: str) -> Booking | None:
        return await db.scalar(
            select(Booking).where(Booking.profile_id == profile_id, Booking.event_id == event_id)
        )
