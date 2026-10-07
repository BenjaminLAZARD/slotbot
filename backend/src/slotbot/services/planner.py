from dataclasses import replace

from slotbot.domain.constraints import parse_constraints
from slotbot.domain.describe import user_part
from slotbot.domain.ranking import nearby, window
from slotbot.domain.types import CalendarEvent, Plan
from slotbot.ports import Geocoder, Provider
from slotbot.schemas import ProfileConfig
from slotbot.services.venues import VenueCatalogue


class Planner:
    """Turn a calendar event into a Plan: where from, which venues, which times, when it opens."""

    def __init__(self, geocoder: Geocoder, catalogue: VenueCatalogue):
        self._geocoder = geocoder
        self._catalogue = catalogue

    async def plan(
        self, event: CalendarEvent, cfg: ProfileConfig, provider: Provider, refresh: bool = False
    ) -> Plan:
        tz = provider.tz
        event = replace(event, start=event.start.astimezone(tz), end=event.end.astimezone(tz))
        constraints, warnings = parse_constraints(user_part(event.description))

        origin = event.location.strip() or cfg.home.strip()
        point = await self._geocoder.locate(origin) if origin else None
        if point is None:
            warnings += (f"could not locate '{origin or 'no location / home set'}'",)
        venues = await self._catalogue.get(provider, refresh)
        ranked = nearby(venues, point, cfg.max_bike_minutes, constraints, cfg.bike_kmh) if point else ()

        flex = cfg.weekend if event.start.weekday() >= 5 else cfg.weekday
        return Plan(
            event=event,
            origin=origin,
            venues=ranked,
            window=window(event.start, flex.before_minutes, flex.after_minutes, constraints),
            opens_at=provider.opens_at(event.start),
            warnings=warnings,
        )
