import asyncio
from datetime import UTC, datetime

from slotbot.ports import Clock


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


async def sleep_until(clock: Clock, at: datetime, chunk: float = 30.0) -> None:
    """Sleep in short chunks against the wall clock.

    asyncio timers use a monotonic clock that stops while a laptop sleeps, so one long sleep
    could wake up hours late; re-checking the wall clock every `chunk` seconds avoids that.
    """
    while (remaining := (at - clock.now()).total_seconds()) > 0:
        await clock.sleep(min(remaining, chunk))
