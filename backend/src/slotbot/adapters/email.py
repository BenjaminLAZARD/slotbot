"""Email notifiers: Resend's HTTP API (preferred) or plain SMTP (e.g. a Gmail app password)."""

import asyncio
import smtplib
from email.message import EmailMessage

import httpx


class ResendNotifier:
    """Resend (resend.com). Use a "Sending access" API key: it can send email and nothing else.

    Without a verified domain, the sender must be onboarding@resend.dev and Resend only delivers
    to the email address of the Resend account itself (other recipients get HTTP 403).
    """

    _URL = "https://api.resend.com/emails"

    def __init__(self, http: httpx.AsyncClient, api_key: str, sender: str):
        self._http = http
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sender = sender

    async def send(self, to: str, subject: str, body: str) -> None:
        r = await self._http.post(
            self._URL,
            json={"from": self._sender, "to": [to], "subject": subject, "text": body},
            headers=self._headers,
        )
        if r.status_code == 403 and "resend.dev" in self._sender:
            raise RuntimeError(
                f"Resend refused {to}: without your own domain it only emails your Resend account address"
            )
        r.raise_for_status()


class SmtpNotifier:
    def __init__(self, host: str, port: int, user: str, password: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password

    async def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = f"slotbot <{self._user}>"
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        await asyncio.to_thread(self._deliver, message)  # smtplib is blocking

    def _deliver(self, message: EmailMessage) -> None:
        with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.send_message(message)
