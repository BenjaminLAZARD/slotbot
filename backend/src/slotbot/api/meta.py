from fastapi import APIRouter, Depends

from slotbot.api.deps import C, current_user
from slotbot.schemas import MetaOut, ProviderOut

router = APIRouter(prefix="/api", tags=["meta"], dependencies=[Depends(current_user)])


@router.get("/meta")
async def meta(c: C) -> MetaOut:
    """What the UI needs to guide setup: which email to share calendars with, which providers exist."""
    return MetaOut(
        service_account_email=c.google.email,
        triggers=c.settings.triggers,
        email_enabled=c.notifier is not None,
        providers=[
            ProviderOut(key=p.key, label=p.label, credential_fields=list(p.credential_fields))
            for p in c.providers.all()
        ],
    )
