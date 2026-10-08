"""Endpoints called by machines, not people: Cloud Scheduler (sync), Cloud Tasks (races), budget alerts."""

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends

from slotbot.api.deps import C, require_job_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_job_token)])


@router.post("/sync")
async def sync_all(c: C) -> dict[str, bool]:
    await c.sync.sync_all()
    return {"ok": True}


@router.post("/race/{booking_id}")
async def race(booking_id: int, c: C) -> dict[str, bool]:
    # Runs inside the request: Cloud Tasks keeps it open (up to 30 min), so Cloud Run keeps the CPU.
    await c.race.run(booking_id)
    return {"ok": True}


@router.post("/budget")
async def budget(envelope: dict[str, Any], c: C) -> dict[str, bool]:
    """Pub/Sub push from a GCP budget: cut billing once actual spend reaches the budget (hard cap)."""
    data = json.loads(base64.b64decode(envelope.get("message", {}).get("data", "") or "e30="))
    cost, cap = float(data.get("costAmount", 0)), float(data.get("budgetAmount", 0))
    log.info("budget notification: %.2f / %.2f %s", cost, cap, data.get("currencyCode", ""))
    if cap > 0 and cost >= cap and c.kill_switch is not None:
        await c.kill_switch.disable_billing()
        return {"billing_disabled": True}
    return {"billing_disabled": False}  # always 2xx so Pub/Sub doesn't redeliver
