"""Sign-in with Google. The browser gets Google's signed credential; we keep a signed session cookie."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from slotbot.api.deps import C
from slotbot.services.accounts import NotInvited

router = APIRouter(prefix="/auth", tags=["auth"])


class SessionOut(BaseModel):
    signed_in: bool
    email: str = ""
    name: str = ""
    sign_in_enabled: bool  # false on localhost without a Google client ID: no login needed
    google_client_id: str = ""


class CredentialIn(BaseModel):
    credential: str  # the ID token handed to the page by Google's sign-in button


@router.get("/session")
async def session(request: Request, c: C) -> SessionOut:
    """Public: lets the page choose between the landing page and the app."""
    if not c.accounts.enabled:
        return SessionOut(signed_in=True, email="local", sign_in_enabled=False)
    email = request.session.get("email", "")
    signed_in = bool(request.session.get("uid")) and c.accounts.invited(email)
    return SessionOut(
        signed_in=signed_in,
        email=email if signed_in else "",
        name=request.session.get("name", "") if signed_in else "",
        sign_in_enabled=True,
        google_client_id=c.accounts.client_id,
    )


@router.post("/google")
async def google(body: CredentialIn, request: Request, c: C) -> SessionOut:
    try:
        user = await c.accounts.sign_in(body.credential)
    except ValueError:
        raise HTTPException(401, "Google sign-in could not be verified; try again") from None
    except NotInvited as e:
        raise HTTPException(403, f"{e} is not on the invite list yet: ask the owner to add you") from None
    request.session.update(uid=user.id, email=user.email, name=user.name)
    return SessionOut(
        signed_in=True,
        email=user.email,
        name=user.name,
        sign_in_enabled=True,
        google_client_id=c.accounts.client_id,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request) -> None:
    request.session.clear()
