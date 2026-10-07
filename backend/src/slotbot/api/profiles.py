from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from slotbot.api.deps import DB, C
from slotbot.domain.ranking import nearby
from slotbot.models import Booking, BookingStatus, Profile
from slotbot.schemas import BookingOut, CredentialsIn, ProfileConfig, ProfileIn, ProfileOut, VenueOut

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("")
async def list_profiles(db: DB) -> list[ProfileOut]:
    return [_out(p) for p in await db.scalars(select(Profile).order_by(Profile.id))]


@router.post("", status_code=201)
async def create_profile(body: ProfileIn, db: DB, c: C) -> ProfileOut:
    _check_provider(c, body.config)
    profile = Profile(name=body.name, config=body.config.model_dump())
    db.add(profile)
    await db.commit()
    return _out(profile)


@router.get("/{profile_id}")
async def get_profile(profile_id: int, db: DB) -> ProfileOut:
    return _out(await _load(db, profile_id))


@router.put("/{profile_id}")
async def update_profile(profile_id: int, body: ProfileIn, db: DB, c: C) -> ProfileOut:
    _check_provider(c, body.config)
    profile = await _load(db, profile_id)
    profile.name, profile.config = body.name, body.config.model_dump()
    await db.commit()
    return _out(profile)


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: int, db: DB, c: C) -> None:
    profile = await _load(db, profile_id)
    pending = await db.scalars(
        select(Booking).where(Booking.profile_id == profile_id, Booking.status == BookingStatus.PENDING)
    )
    for booking in pending:
        if booking.trigger_ref:
            await c.triggers.cancel(booking.trigger_ref)
    await db.delete(profile)
    await db.commit()


@router.put("/{profile_id}/credentials", status_code=204)
async def set_credentials(profile_id: int, body: CredentialsIn, db: DB, c: C) -> None:
    profile = await _load(db, profile_id)
    provider = c.providers.get(ProfileConfig.model_validate(profile.config).provider)
    if missing := [f for f in provider.credential_fields if not body.values.get(f)]:
        raise HTTPException(422, f"missing: {', '.join(missing)}")
    profile.credentials = c.vault.seal({f: body.values[f] for f in provider.credential_fields})
    await db.commit()


@router.get("/{profile_id}/venues")
async def list_venues(profile_id: int, db: DB, c: C, refresh: bool = False) -> list[VenueOut]:
    """Venues in bike range of the profile's home, closest first (refresh=true re-fetches them)."""
    cfg = ProfileConfig.model_validate((await _load(db, profile_id)).config)
    point = await c.geocoder.locate(cfg.home) if cfg.home else None
    if point is None:
        raise HTTPException(422, "set a home address the geocoder can find")
    venues = await c.catalogue.get(c.providers.get(cfg.provider), refresh)
    return [
        VenueOut(id=r.venue.id, name=r.venue.name, address=r.venue.address, minutes=r.minutes)
        for r in nearby(venues, point, cfg.max_bike_minutes, kmh=cfg.bike_kmh)
    ]


@router.post("/{profile_id}/sync")
async def sync_profile(profile_id: int, c: C, refresh_venues: bool = False) -> BookingOut | None:
    """Plan the next candidate event now instead of waiting for the daily sync."""
    try:
        booking = await c.sync.sync_profile(profile_id, refresh_venues)
    except LookupError:
        raise HTTPException(404, "profile not found") from None
    return BookingOut.model_validate(booking) if booking else None


@router.get("/{profile_id}/bookings")
async def list_bookings(profile_id: int, db: DB) -> list[BookingOut]:
    rows = await db.scalars(
        select(Booking).where(Booking.profile_id == profile_id).order_by(Booking.play_start.desc())
    )
    return [BookingOut.model_validate(b) for b in rows]


async def _load(db: DB, profile_id: int) -> Profile:
    if (profile := await db.get(Profile, profile_id)) is None:
        raise HTTPException(404, "profile not found")
    return profile


def _check_provider(c: C, cfg: ProfileConfig) -> None:
    try:
        c.providers.get(cfg.provider)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def _out(p: Profile) -> ProfileOut:
    return ProfileOut(
        id=p.id,
        name=p.name,
        config=ProfileConfig.model_validate(p.config),
        has_credentials=bool(p.credentials),
    )
