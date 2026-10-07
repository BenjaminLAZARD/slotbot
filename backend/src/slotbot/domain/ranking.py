"""Which venues are close enough, which start times are acceptable, and in what order to try them."""

import unicodedata
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt

from slotbot.domain.types import Constraints, GeoPoint, RankedVenue, Slot, Venue, Window

_EARTH_KM = 6371.0
_NO_CONSTRAINTS = Constraints()
_DETOUR = 1.3  # streets are not straight lines; ~1.3x is a common urban detour factor


def bike_minutes(a: GeoPoint, b: GeoPoint, kmh: float = 15.0) -> int:
    """Rough bike time: great-circle distance x detour factor at a steady city pace."""
    dlat, dlon = radians(b.lat - a.lat), radians(b.lon - a.lon)
    h = sin(dlat / 2) ** 2 + cos(radians(a.lat)) * cos(radians(b.lat)) * sin(dlon / 2) ** 2
    km = 2 * _EARTH_KM * asin(sqrt(h))
    return round(km * _DETOUR / kmh * 60)


def nearby(
    venues: Iterable[Venue],
    origin: GeoPoint,
    max_minutes: int,
    constraints: Constraints = _NO_CONSTRAINTS,
    kmh: float = 15.0,
) -> tuple[RankedVenue, ...]:
    """Venues reachable by bike, closest first, filtered by the event's only/avoid lists."""
    limit = constraints.max_bike_minutes or max_minutes
    ranked = sorted(
        (RankedVenue(v, bike_minutes(origin, v.point, kmh)) for v in venues),
        key=lambda r: (r.minutes, r.venue.name),
    )
    return tuple(r for r in ranked if r.minutes <= limit and _allowed(r.venue.name, constraints))


def window(
    start: datetime, before_minutes: int, after_minutes: int | None, constraints: Constraints
) -> Window:
    """Acceptable start times around the requested one; explicit constraints override defaults."""
    earliest = start - timedelta(minutes=before_minutes)
    latest = None if after_minutes is None else start + timedelta(minutes=after_minutes)
    if constraints.earliest:
        earliest = start.replace(hour=constraints.earliest.hour, minute=constraints.earliest.minute)
    if constraints.latest:
        latest = start.replace(hour=constraints.latest.hour, minute=constraints.latest.minute)
    return Window(preferred=start, earliest=earliest, latest=latest)


def candidates(free: Iterable[Slot], venues: Sequence[RankedVenue], win: Window) -> list[Slot]:
    """Free slots worth trying, in order: closest time to the requested one, then closest venue.

    Ties on time distance prefer the later slot (you asked for 19:00; 20:00 beats 18:00).
    """
    minutes = {r.venue.id: r.minutes for r in venues}
    day = win.preferred.date()

    def acceptable(s: Slot) -> bool:
        return (
            s.venue.id in minutes
            and s.start >= win.earliest
            and (win.latest is None or s.start <= win.latest)
            and s.start.astimezone(win.preferred.tzinfo).date() == day
        )

    def order(s: Slot) -> tuple[float, bool, int]:
        delta = (s.start - win.preferred).total_seconds()
        return abs(delta), delta < 0, minutes[s.venue.id]

    return sorted(filter(acceptable, free), key=order)


def _fold(text: str) -> str:
    """Lowercase and strip accents so 'chamartin' matches 'Chamartín'."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def _allowed(name: str, c: Constraints) -> bool:
    folded = _fold(name)
    if c.only and not any(_fold(o) in folded for o in c.only):
        return False
    return not any(_fold(a) in folded for a in c.avoid)
