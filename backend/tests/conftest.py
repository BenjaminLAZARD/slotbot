from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from slotbot.domain.types import CalendarEvent, GeoPoint
from slotbot.models import Base
from slotbot.ports import EventChanges


class FakeClock:
    """Time only moves when someone sleeps."""

    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


class FakeCalendar:
    def __init__(self, events: list[CalendarEvent]):
        self.events = {e.id: e for e in events}

    async def upcoming(self, calendar_id: str, start: datetime, days: int) -> list[CalendarEvent]:
        end = start + timedelta(days=days)
        return sorted((e for e in self.events.values() if start <= e.start < end), key=lambda e: e.start)

    async def get(self, calendar_id: str, event_id: str) -> CalendarEvent | None:
        return self.events.get(event_id)

    async def update(self, calendar_id: str, event_id: str, changes: EventChanges) -> None:
        e = self.events[event_id]
        self.events[event_id] = replace(
            e,
            title=changes.title if changes.title is not None else e.title,
            description=changes.description if changes.description is not None else e.description,
            location=changes.location if changes.location is not None else e.location,
            start=changes.start or e.start,
            end=changes.end or e.end,
        )


class FakeGeocoder:
    async def locate(self, query: str) -> GeoPoint | None:
        return GeoPoint(40.4168, -3.7038)  # Puerta del Sol


class FakeTriggers:
    def __init__(self) -> None:
        self.scheduled: dict[str, tuple[int, datetime]] = {}

    async def schedule(self, booking_id: int, at: datetime) -> str:
        ref = f"t:{booking_id}:{int(at.timestamp())}"
        self.scheduled[ref] = (booking_id, at)
        return ref

    async def cancel(self, ref: str) -> None:
        self.scheduled.pop(ref, None)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 5, 12, 0, tzinfo=UTC))


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
