"""Local-mode stand-in for Cloud Scheduler: re-arm timers after a restart, then sync periodically."""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from slotbot.adapters.clock import sleep_until
from slotbot.models import Booking, BookingStatus
from slotbot.ports import Clock, Triggers
from slotbot.services.sync import SyncService

log = logging.getLogger(__name__)


class LocalLoop:
    def __init__(
        self,
        sessions: async_sessionmaker,
        triggers: Triggers,
        sync: SyncService,
        clock: Clock,
        every: timedelta,
    ):
        self._sessions = sessions
        self._triggers = triggers
        self._sync = sync
        self._clock = clock
        self._every = every
        self._task: asyncio.Task[None] | None = None
        self.next_sync: datetime | None = None  # shown in the UI

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run(self) -> None:
        await self._rearm()
        while True:
            try:
                await self._sync.sync_all()
            except Exception:
                log.exception("periodic sync failed")
            self.next_sync = self._clock.now() + self._every
            await sleep_until(self._clock, self.next_sync)

    async def _rearm(self) -> None:
        """In-process timers die with the process; recreate one per pending booking."""
        async with self._sessions() as db:
            pending = (await db.scalars(select(Booking).where(Booking.status == BookingStatus.PENDING))).all()
            for b in pending:
                b.trigger_ref = await self._triggers.schedule(b.id, max(b.trigger_at, self._clock.now()))
            await db.commit()
        log.info("re-armed %d pending booking(s)", len(pending))
