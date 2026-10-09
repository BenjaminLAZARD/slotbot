from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from slotbot.container import Container
from slotbot.models import Profile


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(c: Annotated[Container, Depends(get_container)]) -> AsyncIterator[AsyncSession]:
    async with c.sessions() as session:
        yield session


C = Annotated[Container, Depends(get_container)]
DB = Annotated[AsyncSession, Depends(get_db)]


@dataclass(frozen=True)
class Me:
    id: int
    email: str


async def current_user(request: Request, c: C) -> Me:
    """The signed-in person, from the signed session cookie: no database read for strangers."""
    if not c.accounts.enabled:
        user = await c.accounts.local_user()
        return Me(user.id, user.email)
    uid, email = request.session.get("uid"), request.session.get("email", "")
    if not uid or not c.accounts.invited(email):  # removed from the invite list: out at once
        raise HTTPException(401, "sign in first")
    return Me(uid, email)


CurrentUser = Annotated[Me, Depends(current_user)]


async def owned_profile(profile_id: int, me: CurrentUser, db: DB) -> Profile:
    profile = await db.get(Profile, profile_id)
    if profile is None or profile.owner_id != me.id:  # someone else's profile looks missing
        raise HTTPException(404, "profile not found")
    return profile


OwnedProfile = Annotated[Profile, Depends(owned_profile)]


async def require_job_token(request: Request, c: C) -> None:
    """Machine callers: the shared secret (header or ?token=) and, once public, a Google-signed token."""
    expected = c.settings.job_token
    # Header for Cloud Tasks / Scheduler; query parameter for Pub/Sub push, which can't set headers.
    given = request.headers.get("X-Job-Token") or request.query_params.get("token")
    if expected and given != expected:
        raise HTTPException(403, "bad job token")
    if caller := c.settings.job_caller:
        token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        try:
            identity = await c.identity.verify(token, c.settings.public_url)
        except ValueError:
            raise HTTPException(403, "bad caller token") from None
        if identity.email != caller.lower():
            raise HTTPException(403, "unexpected caller")
