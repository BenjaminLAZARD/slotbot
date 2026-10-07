from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from slotbot.container import Container


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(c: Annotated[Container, Depends(get_container)]) -> AsyncIterator[AsyncSession]:
    async with c.sessions() as session:
        yield session


def require_job_token(request: Request, c: Annotated[Container, Depends(get_container)]) -> None:
    """Cloud Tasks / Cloud Scheduler send the shared secret; local mode may leave it empty."""
    expected = c.settings.job_token
    if expected and request.headers.get("X-Job-Token") != expected:
        raise HTTPException(403, "bad job token")


C = Annotated[Container, Depends(get_container)]
DB = Annotated[AsyncSession, Depends(get_db)]
