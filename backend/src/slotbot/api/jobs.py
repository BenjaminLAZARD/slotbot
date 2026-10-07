"""Endpoints called by schedulers, not people: Cloud Scheduler (daily sync), Cloud Tasks (races)."""

from fastapi import APIRouter, Depends

from slotbot.api.deps import C, require_job_token

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
