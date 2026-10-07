from datetime import timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker

from slotbot.domain.types import GeoPoint, Venue
from slotbot.models import VenueCache
from slotbot.ports import Clock, Provider

TTL = timedelta(hours=24)


class VenueCatalogue:
    """Provider venue lists, cached in the database (they change rarely; fetching is slow)."""

    def __init__(self, sessions: async_sessionmaker, clock: Clock):
        self._sessions = sessions
        self._clock = clock

    async def get(self, provider: Provider, refresh: bool = False) -> list[Venue]:
        now = self._clock.now()
        async with self._sessions() as db:
            row = await db.get(VenueCache, provider.key)
            if row and not refresh and now - row.fetched_at < TTL:
                return [_load(v) for v in row.venues]
            venues = await provider.venues()
            data = [_dump(v) for v in venues]
            if row:
                row.venues, row.fetched_at = data, now
            else:
                db.add(VenueCache(provider=provider.key, venues=data, fetched_at=now))
            await db.commit()
            return venues


def _dump(v: Venue) -> dict:
    return {"id": v.id, "name": v.name, "address": v.address, "lat": v.point.lat, "lon": v.point.lon}


def _load(d: dict) -> Venue:
    return Venue(d["id"], d["name"], d["address"], GeoPoint(d["lat"], d["lon"]))
