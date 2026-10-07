from fastapi import APIRouter, HTTPException

from slotbot.api.deps import DB, C
from slotbot.models import Booking, BookingStatus
from slotbot.schemas import BookingOut

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


@router.post("/{booking_id}/retry", status_code=202)
async def retry(booking_id: int, db: DB, c: C) -> BookingOut:
    """Race again now, e.g. after a failure. Only once the booking window is open."""
    booking = await db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "booking not found")
    if booking.status in (BookingStatus.RACING, BookingStatus.BOOKED):
        raise HTTPException(409, f"booking is {booking.status}")
    now = c.clock.now()
    if now < booking.trigger_at:
        raise HTTPException(409, f"window not open yet; the race is scheduled for {booking.trigger_at}")
    if booking.trigger_ref:
        await c.triggers.cancel(booking.trigger_ref)
    booking.status = BookingStatus.PENDING
    booking.trigger_ref = await c.triggers.schedule(booking.id, now)
    await db.commit()
    return BookingOut.model_validate(booking)
