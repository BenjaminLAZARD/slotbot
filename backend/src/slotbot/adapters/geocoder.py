"""Turn an event location ("Chamberí, Madrid") into coordinates with OpenStreetMap's Nominatim."""

import asyncio
import re
import time

import httpx

from slotbot.domain.types import GeoPoint

_URL = "https://nominatim.openstreetmap.org/search"
_LATLON = re.compile(r"^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$")


class Nominatim:
    """Free geocoder; its policy asks for a descriptive User-Agent and at most 1 request/s.

    We send a handful of requests per day, and cache results for the process lifetime.
    """

    def __init__(self, http: httpx.AsyncClient, user_agent: str):
        self._http = http
        self._headers = {"User-Agent": user_agent}
        self._cache: dict[str, GeoPoint | None] = {}
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def locate(self, query: str) -> GeoPoint | None:
        if m := _LATLON.match(query):  # "40.43, -3.70" skips the network entirely
            return GeoPoint(float(m[1]), float(m[2]))
        key = query.strip().lower()
        if key not in self._cache:
            async with self._lock:  # their policy: at most one request per second
                await asyncio.sleep(max(0.0, 1.0 - (time.monotonic() - self._last)))
                self._last = time.monotonic()
                r = await self._http.get(
                    _URL, params={"q": query, "format": "jsonv2", "limit": "1"}, headers=self._headers
                )
            r.raise_for_status()
            hits = r.json()
            self._cache[key] = GeoPoint(float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
        return self._cache[key]
