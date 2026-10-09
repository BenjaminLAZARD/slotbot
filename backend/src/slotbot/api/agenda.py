from fastapi import APIRouter, Depends, HTTPException

from slotbot.api.deps import C, owned_profile
from slotbot.schemas import ActionOut, AgendaEventOut, AgendaOut
from slotbot.services.agenda import ActionRefused, AgendaItem

router = APIRouter(
    prefix="/api/profiles/{profile_id}", tags=["agenda"], dependencies=[Depends(owned_profile)]
)


@router.get("/agenda")
async def agenda(profile_id: int, c: C) -> AgendaOut:
    """The next events in the calendar with their stage, booking opening and bot wake-up times."""
    try:
        a = await c.agenda.agenda(profile_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    return AgendaOut(
        events=[_out(i) for i in a.items],
        next_wake=_out(a.next_wake) if a.next_wake else None,
        next_sync=a.next_sync,
    )


@router.post("/events/{event_id}/cancel")
async def cancel(profile_id: int, event_id: str, c: C) -> ActionOut:
    """Stop the bot for this event; a paid booking is cancelled on the site (refund to the wallet)."""
    return ActionOut(detail=await _run(c.agenda.cancel(profile_id, event_id)))


@router.post("/events/{event_id}/reset")
async def reset(profile_id: int, event_id: str, c: C) -> ActionOut:
    """Turn the event back into a fresh candidate; the bot plans it again (and races if open)."""
    await _run(c.agenda.reset(profile_id, event_id))
    return ActionOut(detail="reset to candidate")


async def _run(action):  # type: ignore[no-untyped-def]
    try:
        return await action
    except LookupError as e:
        raise HTTPException(404, str(e)) from None
    except ActionRefused as e:
        raise HTTPException(409, str(e)) from None
    except Exception as e:  # booking-site failures: show the site's own message
        raise HTTPException(502, f"{type(e).__name__}: {e}") from None


def _out(i: AgendaItem) -> AgendaEventOut:
    e = i.event
    return AgendaEventOut(
        event_id=e.id,
        title=e.title,
        start=e.start,
        end=e.end,
        location=e.location,
        stage=i.stage,
        booking_id=i.booking_id,
        opens_at=i.opens_at,
        wakes_at=i.wakes_at,
        court=i.court,
        actions=list(i.actions),
    )
