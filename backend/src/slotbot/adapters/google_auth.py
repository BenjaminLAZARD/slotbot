import asyncio
import json
from pathlib import Path

import google.auth
import google.auth.exceptions
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from slotbot.errors import ConfigError

SCOPES = (
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/cloud-platform",  # Cloud Tasks; IAM roles still apply
)


class GoogleToken:
    """OAuth access tokens for the bot's Google identity (a service account).

    `setting` is a key-file path, the key JSON itself, or empty for ambient credentials
    (on Cloud Run: the service's own identity). Loaded lazily so the app boots without it.
    """

    def __init__(self, setting: str):
        self._setting = setting
        self._creds: Credentials | None = None

    def _credentials(self) -> Credentials:
        if self._creds is None:
            value = self._setting
            try:
                if not value.strip():
                    self._creds, _ = google.auth.default(scopes=SCOPES)
                else:
                    raw = value if value.lstrip().startswith("{") else Path(value).read_text()
                    info = json.loads(raw)
                    self._creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            except (OSError, ValueError, google.auth.exceptions.DefaultCredentialsError) as e:
                raise ConfigError(f"Google service account not configured ({e})") from e
        return self._creds

    @property
    def email(self) -> str:
        try:
            return getattr(self._credentials(), "service_account_email", "") or ""
        except Exception:
            return ""

    async def headers(self) -> dict[str, str]:
        creds = self._credentials()
        if not creds.valid:  # google-auth refresh is blocking; keep it off the event loop
            await asyncio.to_thread(creds.refresh, Request())
        return {"Authorization": f"Bearer {creds.token}"}
