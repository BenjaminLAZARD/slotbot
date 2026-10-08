"""Google Calendar REST API (v3) over httpx, authenticated as the bot's service account.

Each user shares their calendar with the service account's email ("Make changes to events").
"""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from slotbot.adapters.google_auth import GoogleToken
from slotbot.domain.types import CalendarEvent
from slotbot.errors import ConfigError
from slotbot.ports import EventChanges

_API = "https://www.googleapis.com/calendar/v3/calendars"


class GoogleCalendar:
    def __init__(self, http: httpx.AsyncClient, token: GoogleToken):
        self._http = http
        self._token = token

    async def upcoming(self, calendar_id: str, start: datetime, days: int) -> list[CalendarEvent]:
        params = {
            "timeMin": start.isoformat(),
            "timeMax": (start + timedelta(days=days)).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": "250",
        }
        r = await self._http.get(
            f"{_API}/{quote(calendar_id)}/events", params=params, headers=await self._token.headers()
        )
        if r.status_code in (403, 404):  # Google answers 404 when the calendar isn't shared with us
            raise ConfigError(
                f"Google can't see calendar '{calendar_id}'. Check the ID, and share the calendar with "
                f"{self._token.email} ('Make changes to events')."
            )
        r.raise_for_status()
        return [e for item in r.json().get("items", []) if (e := _event(item))]

    async def get(self, calendar_id: str, event_id: str) -> CalendarEvent | None:
        r = await self._http.get(
            f"{_API}/{quote(calendar_id)}/events/{quote(event_id)}",
            headers=await self._token.headers(),
        )
        if r.status_code in (404, 410):
            return None
        r.raise_for_status()
        item = r.json()
        return None if item.get("status") == "cancelled" else _event(item)

    async def update(self, calendar_id: str, event_id: str, changes: EventChanges) -> None:
        body: dict[str, Any] = {}
        if changes.title is not None:
            body["summary"] = changes.title
        if changes.description is not None:
            body["description"] = changes.description
        if changes.location is not None:
            body["location"] = changes.location
        if changes.start is not None:
            body["start"] = {"dateTime": changes.start.isoformat()}
        if changes.end is not None:
            body["end"] = {"dateTime": changes.end.isoformat()}
        r = await self._http.patch(
            f"{_API}/{quote(calendar_id)}/events/{quote(event_id)}",
            json=body,
            headers=await self._token.headers(),
        )
        r.raise_for_status()


def _event(item: dict[str, Any]) -> CalendarEvent | None:
    start, end = item.get("start", {}), item.get("end", {})
    if "dateTime" not in start:  # all-day events carry no time to book
        return None
    return CalendarEvent(
        id=item["id"],
        title=item.get("summary", ""),
        start=datetime.fromisoformat(start["dateTime"]),
        end=datetime.fromisoformat(end["dateTime"]),
        location=item.get("location", ""),
        description=item.get("description", ""),
    )
