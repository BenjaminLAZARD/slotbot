"""Parse the `key: value` lines a user writes in a calendar event description.

Supported keys (case-insensitive):
    earliest: 18:00        earliest acceptable start (overrides the weekday/weekend default)
    latest: 21:30          latest acceptable start (overrides the default)
    only: Chopera, Gallur  restrict to venues whose name contains one of these
    avoid: Casa de Campo   exclude venues whose name contains one of these
    max_bike: 20           override the max bike minutes for this event
"""

import html
import re
from datetime import time

from slotbot.domain.types import Constraints

_BREAK = re.compile(r"<\s*(br|/p|/div|/li)\s*/?>", re.I)
_TAG = re.compile(r"<[^>]+>")
_LINE = re.compile(r"^\s*([a-z_ ]+?)\s*:\s*(.+?)\s*$", re.I)
_TIME = re.compile(r"^(\d{1,2})(?:[:h.](\d{2}))?h?$", re.I)
_KEYS = {"earliest", "latest", "only", "avoid", "max_bike"}


def plain_text(description: str) -> str:
    """Google Calendar stores descriptions edited in its web UI as HTML."""
    return html.unescape(_TAG.sub("", _BREAK.sub("\n", description)))


def parse_constraints(description: str) -> tuple[Constraints, tuple[str, ...]]:
    """Return the constraints plus human-readable warnings for lines we could not read."""
    fields: dict[str, str] = {}
    for line in plain_text(description).splitlines():
        if (m := _LINE.match(line)) and (key := m[1].lower().replace(" ", "_")) in _KEYS:
            fields[key] = m[2]

    warnings: list[str] = []

    def read_time(key: str) -> time | None:
        if key not in fields:
            return None
        if m := _TIME.match(fields[key].replace(" ", "")):
            hour, minute = int(m[1]), int(m[2] or 0)
            if hour < 24 and minute < 60:
                return time(hour, minute)
        warnings.append(f"ignored '{key}: {fields[key]}' (expected a time like 21:00)")
        return None

    def read_names(key: str) -> tuple[str, ...]:
        return tuple(n.strip() for n in fields.get(key, "").split(",") if n.strip())

    max_bike = None
    if "max_bike" in fields:
        if fields["max_bike"].isdigit():
            max_bike = int(fields["max_bike"])
        else:
            warnings.append(f"ignored 'max_bike: {fields['max_bike']}' (expected minutes)")

    constraints = Constraints(
        earliest=read_time("earliest"),
        latest=read_time("latest"),
        only=read_names("only"),
        avoid=read_names("avoid"),
        max_bike_minutes=max_bike,
    )
    return constraints, tuple(warnings)
