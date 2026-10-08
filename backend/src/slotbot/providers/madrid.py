"""Madrid municipal sports centres (Ayuntamiento de Madrid): tennis court rentals.

Booking rules published by the city's Área Delegada de Deporte (in force since 2023-02-01):
- One-off tennis rentals open "7 days ahead, the day of play included", i.e. on D-6.
- Free cancellation until 24 h before; a second no-show suspends advance booking for 48 h.
- Any booking can be cancelled within 10 minutes of confirmation (handy if the bot mis-books).
The opening *hour* is not published: it is a setting (SLOTBOT_MADRID_OPENS_AT), measured with
scripts/probe_madrid_opening.py. The site itself says when a day is open (its "dates" list).

Venues are the centres the booking site lists for tennis (anonymous access), placed on the map with
the city's open-data coordinates, or by geocoding their address when open data has no match.
"""

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from types import TracebackType
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from slotbot.domain.types import BookingResult, GeoPoint, Outcome, Slot, Venue
from slotbot.errors import AbortRace
from slotbot.ports import Geocoder
from slotbot.providers.deportesweb import (
    WALLET,
    DeportesWeb,
    GridCell,
    alert_text,
    page_texts,
    parse_cart,
)

OPEN_DATA = "https://datos.madrid.es/egob/catalogo/200186-0-polideportivos.json"
SLOT_LENGTH = timedelta(minutes=60)  # usage "Tenis 60 minutos"


class MadridTennis:
    key = "madrid-tennis"
    label = "Madrid · municipal tennis courts"
    tz = ZoneInfo("Europe/Madrid")
    credential_fields = ("email", "password")  # Madrid Móvil / DeportesWeb account

    def __init__(
        self,
        http: httpx.AsyncClient,
        geocoder: Geocoder,
        opens_at: str = "00:00",
        days_before: int = 6,
        light: bool = True,
    ):
        self._http = http
        self._geocoder = geocoder
        self._opens_at = time.fromisoformat(opens_at)
        self._days_before = days_before
        self._light = light

    def opens_at(self, play_start: datetime) -> datetime:
        day = play_start.astimezone(self.tz).date() - timedelta(days=self._days_before)
        return datetime.combine(day, self._opens_at, self.tz)

    async def venues(self) -> list[Venue]:
        async with DeportesWeb() as web:
            await web.browse_anonymously()
            await web.open_tennis()
            facilities = web.facilities()
        points = await self._open_data_points()
        venues = []
        for f in facilities:
            point = points.get(_key(f["name"])) or await self._geocoder.locate(_plain_address(f["address"]))
            if point:
                venues.append(Venue(f["code"], f["name"], f["address"], point))
        return venues

    def session(self, credentials: dict[str, str]) -> "MadridSession":
        return MadridSession(credentials, self.tz, self._light)

    async def _open_data_points(self) -> dict[str, GeoPoint]:
        r = await self._http.get(OPEN_DATA)
        r.raise_for_status()
        return {
            _key(c["title"]): GeoPoint(float(c["location"]["latitude"]), float(c["location"]["longitude"]))
            for c in r.json()["@graph"]
            if c.get("location")
        }


class MadridSession:
    """A logged-in DeportesWeb session. The site keeps one centre + date selected per page, so we
    remember what is loaded and only re-navigate when the race asks for another centre."""

    def __init__(self, credentials: dict[str, str], tz: ZoneInfo, light: bool):
        self._credentials = credentials
        self._tz = tz
        self._light = light
        self._web = DeportesWeb()
        self._facility: str | None = None
        self._usage: dict[str, Any] = {}
        self._loaded: tuple[str, date] | None = None
        self._cells: dict[str, GridCell] = {}

    async def __aenter__(self) -> "MadridSession":
        await self._web.login(self._credentials["email"], self._credentials["password"])
        await self._web.open_tennis()
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._web.__aexit__()

    async def is_open(self, day: date, venue: Venue) -> bool:
        await self._select(venue.id)  # one request; the answer lists the bookable days
        return day.isoformat() in self._usage.get("dates", [])

    async def free_slots(self, day: date, venue: Venue) -> list[Slot]:
        if self._loaded and self._loaded[0] == venue.id:
            cells = await self._web.day(day)  # this centre's grid is on screen: one request
        else:
            if self._facility != venue.id:
                await self._select(venue.id)
            if day.isoformat() not in self._usage.get("dates", []):
                return []
            await self._web.select_usage(self._usage)
            cells = await self._web.day(day)
        self._loaded = (venue.id, day)
        slots = []
        for cell in cells:
            start = datetime.combine(day, time.fromisoformat(cell.start), self._tz)
            court = cell.court_name.removesuffix(venue.name).strip()
            self._cells[cell.cell_id] = cell
            slots.append(Slot(venue, start, start + SLOT_LENGTH, court=court, ref=cell.cell_id))
        return slots

    async def book(self, slot: Slot) -> BookingResult:
        day = slot.start.date()
        if self._loaded != (slot.venue.id, day):  # the site books from the grid currently shown
            await self.free_slots(day, slot.venue)
        if (cell := self._cells.get(slot.ref)) is None:
            return BookingResult(Outcome.TAKEN, "no longer offered")

        reserved = await self._web.reserve(cell, self._light)
        self._facility = self._loaded = None  # the next step leaves the tennis page
        if not reserved.redirect:
            alert = alert_text(reserved) or "refused by the site"
            # Not about this slot (signed out, suspended, daily limit): every other try would fail too.
            if re.search(r"identific|suspendid|suspensi|no se permiten m", alert, re.I):
                raise AbortRace(f"the site refused the account: {alert}")
            return BookingResult(Outcome.TAKEN, alert)
        await self._web.follow(reserved)

        # From here an unpaid reservation sits in the cart and blocks further selections, so any
        # reason not to pay ends the race: never pile up reservations the bot won't pay for.
        cart = parse_cart(self._web.html)
        if cart.items != 1 or cell.start not in cart.texts:
            raise AbortRace(
                f"the cart holds {cart.items} items, not just ours: nothing paid, check deportesweb"
            )
        if cart.wallet is None or cart.total is None or cart.wallet < cart.total:
            raise AbortRace(
                f"wallet {cart.wallet} € < price {cart.total} €: the slot waits unpaid in your cart"
            )

        paid = await self._web.confirm_cart(WALLET)
        if not paid.redirect:
            raise AbortRace(f"payment refused: {alert_text(paid) or 'no confirmation'}")
        await self._web.follow(paid)
        texts = page_texts(self._web.html)
        if "Confirmado" not in texts:
            raise AbortRace("payment not confirmed: check deportesweb")
        # The cart number is what cancelling needs (Consultar {cartCode} -> RefundCart).
        cart_code = next((texts[i + 1] for i, t in enumerate(texts[:-1]) if t == "Carrito"), "")
        left = cart.wallet - cart.total
        note = f"paid {cart.total:.2f} € from the wallet, {left:.2f} € left"
        if left < cart.total:
            note += " (top it up before the next booking)"
        return BookingResult(Outcome.BOOKED, note, reference=cart_code, price=cart.total, balance=left)

    async def _select(self, facility: str) -> None:
        if self._web.page is None or "ReservaEspacios" not in self._web.page.url:
            await self._web.open_tennis()  # back from the cart after a refused payment
        self._usage = await self._web.select_facility(facility)
        self._facility, self._loaded = facility, None
        if not self._web.person_code:  # sent with every reservation; without it the site refuses
            raise AbortRace("signed in, but the site did not return the account's person code")


def _key(name: str) -> str:
    """Comparable centre name: 'Centro Deportivo Municipal La Chopera' == 'La Chopera'."""
    name = re.sub(r"^(Centro Deportivo Municipal|CDM)\s+", "", name.strip(), flags=re.I)
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()


def _plain_address(address: str) -> str:
    """'Calle X, 99 (Moncloa - Aravaca), 28023, Madrid' -> 'Calle X, 99, 28023, Madrid' for geocoding."""
    return re.sub(r"\s*\([^)]*\)", "", address)
