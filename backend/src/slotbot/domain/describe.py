"""Render the bot's section of a calendar event description.

The description is split in two at MARKER: everything above belongs to the user (and is where
they write constraints); everything below is rewritten by the bot on every update.
"""

import html
import re
from collections.abc import Sequence
from datetime import datetime

from slotbot.domain.types import Outcome, Plan, RaceReport

MARKER = "──────── slotbot ────────"
_HTML = re.compile(r"<(br|p|div|b|i|u|a|ul|ol|li|span)\b", re.I)
_MAX_ATTEMPT_LINES = 40


def has_marker(title: str, marker: str) -> bool:
    return marker.lower() in title.lower()


def retitle(title: str, new: str, *olds: str) -> str:
    """Swap the first stage marker found ('Candidate Tennis w/ Ana' -> 'Pending Tennis w/ Ana')."""
    for old in olds:
        if (i := title.lower().find(old.lower())) >= 0:
            return title[:i] + new + title[i + len(old) :]
    return new


def user_part(description: str) -> str:
    return description.split(MARKER, 1)[0].rstrip()


def compose(description: str, lines: Sequence[str]) -> str:
    """Keep the user's part untouched and replace the bot section with `lines`."""
    user = user_part(description)
    if _HTML.search(user):  # edited in Google's web UI: stay in HTML so line breaks survive
        sep, body = "<br>", [html.escape(line) for line in (MARKER, *lines)]
    else:
        sep, body = "\n", [MARKER, *lines]
    section = sep.join(body)
    return f"{user}{sep}{sep}{section}" if user else section


def plan_lines(plan: Plan, status: str) -> list[str]:
    w = plan.window
    until = _hm(w.latest) if w.latest else "close"
    lines = [
        f"Status: {status} · booking opens {_day(plan.opens_at)}",
        f"Wanted: {_day(w.preferred)} · accepts {_hm(w.earliest)} → {until}",
        f"From: {plan.origin} · {len(plan.venues)} venue(s) in bike range:",
        *(f"  {i}. {r.venue.name} — {r.minutes} min" for i, r in enumerate(plan.venues, 1)),
    ]
    lines += [f"⚠ {warning}" for warning in plan.warnings]
    return lines


def result_lines(plan: Plan, report: RaceReport) -> list[str]:
    if report.booked:
        slot = report.booked
        ref = f" (ref {report.reference})" if report.reference else ""
        head = f"Result: BOOKED {slot.label} · {_day(slot.start)}–{_hm(slot.end)}{ref}"
    else:
        head = f"Result: FAILED · {report.reason or 'no acceptable slot'}"
    status = "booked" if report.booked else "failed"
    tz = plan.event.start.tzinfo
    attempts = [
        f"  {a.at.astimezone(tz):%H:%M:%S}  {a.venue} {_hm(a.start) if a.start else ''} → {a.outcome}"
        + (f" ({a.detail})" if a.detail and a.outcome is not Outcome.BOOKED else "")
        for a in report.attempts[-_MAX_ATTEMPT_LINES:]
    ]
    skipped = len(report.attempts) - len(attempts)
    return [
        head,
        *([f"Payment: {report.note}"] if report.note else []),
        *plan_lines(plan, status),
        f"Attempts ({len(report.attempts)}):" + (f" last {len(attempts)} shown" if skipped else ""),
        *(attempts or ["  none"]),
    ]


def _day(dt: datetime) -> str:
    return f"{dt:%a %d %b %H:%M}"


def _hm(dt: datetime) -> str:
    return f"{dt:%H:%M}"
