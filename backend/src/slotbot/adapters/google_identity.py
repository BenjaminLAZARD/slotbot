"""Verifies Google-signed ID tokens: "Sign in with Google" and the OIDC tokens of Google's schedulers."""

import base64
import json
from datetime import datetime, timedelta

import httpx
from google.auth import jwt

from slotbot.ports import Clock, Identity

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"  # Google's current signing keys (PEM by key ID)
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
REFRESH = timedelta(hours=1)


class GoogleIdentity:
    def __init__(self, http: httpx.AsyncClient, clock: Clock):
        self._http = http
        self._clock = clock
        self._certs: dict[str, str] = {}
        self._fetched: datetime | None = None

    async def verify(self, token: str, audience: str) -> Identity:
        if not token:
            raise ValueError("no token")
        claims = jwt.decode(
            token, certs=await self._keys(self._key_id(token)), audience=audience, clock_skew_in_seconds=30
        )
        if claims.get("iss") not in ISSUERS:
            raise ValueError("not issued by Google")
        if not claims.get("email") or not claims.get("email_verified"):
            raise ValueError("token carries no verified email")
        return Identity(email=claims["email"].lower(), subject=claims["sub"], name=claims.get("name", ""))

    async def _keys(self, key_id: str) -> dict[str, str]:
        """Cached for an hour, refetched for an unknown key; on a fetch failure the old keys still serve
        (Google keeps a retired key valid for days), so a blip at Google can't make a race miss its slot."""
        now = self._clock.now()
        if key_id not in self._certs or self._fetched is None or now - self._fetched > REFRESH:
            try:
                r = await self._http.get(CERTS_URL)
                r.raise_for_status()
                self._certs, self._fetched = r.json(), now
            except httpx.HTTPError:
                if not self._certs:
                    raise
        return self._certs

    @staticmethod
    def _key_id(token: str) -> str:
        head = token.split(".")[0]
        try:
            header = json.loads(base64.urlsafe_b64decode(head + "=" * (-len(head) % 4)))
        except ValueError:  # bad base64 or JSON
            raise ValueError("malformed token") from None
        return str(header.get("kid", ""))
