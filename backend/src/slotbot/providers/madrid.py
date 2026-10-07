"""Madrid municipal sports centres (Ayuntamiento de Madrid): tennis court rentals.

Booking rules published by the city's Área Delegada de Deporte (in force since 2023-02-01):
- One-off tennis rentals open "7 days ahead, the day of play included", i.e. on D-6.
- Free cancellation until 24 h before; a second no-show suspends advance booking for 48 h.
- Any booking can be cancelled within 10 minutes of confirmation (handy if the bot mis-books).
The opening *hour* is not published, so it is a setting (SLOTBOT_MADRID_OPENS_AT) until verified.

Venues come from the city's open-data catalogue for now. Once the DeportesWeb API is captured,
they should come from the booking system itself, merged with these coordinates by name.
"""

import re
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from types import TracebackType
from zoneinfo import ZoneInfo

import httpx

from slotbot.domain.types import BookingResult, GeoPoint, Slot, Venue

OPEN_DATA = "https://datos.madrid.es/egob/catalogo/200186-0-polideportivos.json"
_TENNIS = ("pistadetenis", "pistasdetenis", "(tenis")  # matched with all whitespace removed


class MadridTennis:
    key = "madrid-tennis"
    label = "Madrid · municipal tennis courts"
    tz = ZoneInfo("Europe/Madrid")
    credential_fields = ("email", "password")  # Madrid Móvil / DeportesWeb account

    def __init__(self, http: httpx.AsyncClient, opens_at: str = "00:00", days_before: int = 6):
        self._http = http
        self._opens_at = time.fromisoformat(opens_at)
        self._days_before = days_before

    def opens_at(self, play_start: datetime) -> datetime:
        day = play_start.astimezone(self.tz).date() - timedelta(days=self._days_before)
        return datetime.combine(day, self._opens_at, self.tz)

    async def venues(self) -> list[Venue]:
        r = await self._http.get(OPEN_DATA)
        r.raise_for_status()
        return [_venue(c) for c in r.json()["@graph"] if _has_tennis(c)]

    def session(self, credentials: dict[str, str]) -> "DeportesWebSession":
        return DeportesWebSession(self._http, credentials)


class DeportesWebSession:
    """Logged-in session on deportesweb.madrid.es (same account as the Madrid Móvil app).

    NOT WIRED YET. The site's API is private: login, centre/court list, day availability and
    booking (paid from the in-app wallet) must first be captured from a real browser session.
    See docs/madrid-api.md.
    """

    def __init__(self, http: httpx.AsyncClient, credentials: dict[str, str]):
        self._http = http
        self._credentials = credentials

    async def __aenter__(self) -> "DeportesWebSession":
        raise NotImplementedError("Madrid booking API not wired yet (see docs/madrid-api.md)")

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    async def free_slots(self, day: date, venues: Sequence[Venue]) -> list[Slot]:
        raise NotImplementedError

    async def book(self, slot: Slot) -> BookingResult:
        raise NotImplementedError


def _has_tennis(centre: dict) -> bool:
    services = re.sub(r"\s+", "", centre.get("organization", {}).get("services", "")).lower()
    return any(marker in services for marker in _TENNIS)


def _venue(centre: dict) -> Venue:
    name = re.sub(r"^Centro Deportivo Municipal\s+", "CDM ", centre["title"].strip())
    loc = centre["location"]
    return Venue(
        id=f"od-{centre['id']}",
        name=name,
        address=centre.get("address", {}).get("street-address", "").title(),
        point=GeoPoint(float(loc["latitude"]), float(loc["longitude"])),
    )
