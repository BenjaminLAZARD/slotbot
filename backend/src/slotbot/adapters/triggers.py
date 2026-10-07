"""Two ways to call `race(booking_id)` at a given time.

- CloudTasksTriggers (prod): Google Cloud Tasks POSTs /jobs/race/{id} at the exact time, so the
  Cloud Run service can scale to zero in between.
- LocalTriggers (dev / OrbStack): plain asyncio timers inside the API process.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx

from slotbot.adapters.clock import sleep_until
from slotbot.adapters.google_auth import GoogleToken
from slotbot.ports import Clock

log = logging.getLogger(__name__)
_API = "https://cloudtasks.googleapis.com/v2"


class CloudTasksTriggers:
    def __init__(
        self, http: httpx.AsyncClient, token: GoogleToken, queue: str, public_url: str, job_token: str
    ):
        self._http = http
        self._token = token
        self._queue = queue
        self._url = public_url.rstrip("/")
        self._job_token = job_token

    async def schedule(self, booking_id: int, at: datetime) -> str:
        headers = await self._token.headers()  # first: resolves the service-account email on Cloud Run
        # Deterministic name: re-scheduling the same booking at the same time is a no-op (409).
        name = f"{self._queue}/tasks/booking-{booking_id}-{int(at.timestamp())}"
        task = {
            "name": name,
            "scheduleTime": at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "dispatchDeadline": "1800s",  # max for HTTP targets; a race needs ~lead + retry window
            "httpRequest": {
                "httpMethod": "POST",
                "url": f"{self._url}/jobs/race/{booking_id}",
                "headers": {"X-Job-Token": self._job_token},
                # Signed identity token so a private (no-public-access) Cloud Run service accepts it.
                "oidcToken": {"serviceAccountEmail": self._token.email, "audience": self._url},
            },
        }
        r = await self._http.post(f"{_API}/{self._queue}/tasks", json={"task": task}, headers=headers)
        if r.status_code != 409:
            r.raise_for_status()
        return name

    async def cancel(self, ref: str) -> None:
        r = await self._http.delete(f"{_API}/{ref}", headers=await self._token.headers())
        if r.status_code != 404:
            r.raise_for_status()


class LocalTriggers:
    """In-process timers. Lost on restart, so the app re-schedules pending bookings at startup."""

    def __init__(self, clock: Clock):
        self._clock = clock
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self.fire: Callable[[int], Awaitable[None]] | None = None  # set once the race service exists

    async def schedule(self, booking_id: int, at: datetime) -> str:
        ref = f"local:{booking_id}:{int(at.timestamp())}"
        await self.cancel(ref)
        self._tasks[ref] = asyncio.create_task(self._run(ref, booking_id, at))
        return ref

    async def cancel(self, ref: str) -> None:
        if task := self._tasks.pop(ref, None):
            task.cancel()

    async def _run(self, ref: str, booking_id: int, at: datetime) -> None:
        try:
            await sleep_until(self._clock, at)
            assert self.fire is not None
            await self.fire(booking_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("race for booking %s crashed", booking_id)
        finally:
            if self._tasks.get(ref) is asyncio.current_task():  # not replaced by a re-schedule
                del self._tasks[ref]
