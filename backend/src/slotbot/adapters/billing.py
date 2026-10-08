"""Spending kill switch: detach the GCP project from its billing account (stops all paid services).

Google budgets only alert; this is Google's documented way to turn an alert into a hard cap.
The service account needs the "Project Billing Manager" role on the project.
"""

import logging

import httpx

from slotbot.adapters.google_auth import GoogleToken

log = logging.getLogger(__name__)


class BillingKillSwitch:
    def __init__(self, http: httpx.AsyncClient, token: GoogleToken, project: str):
        self._http = http
        self._token = token
        self._project = project

    async def disable_billing(self) -> None:
        url = f"https://cloudbilling.googleapis.com/v1/projects/{self._project}/billingInfo"
        r = await self._http.put(url, json={"billingAccountName": ""}, headers=await self._token.headers())
        r.raise_for_status()
        log.warning("billing disabled for project %s (budget cap reached)", self._project)
