"""Plain-text email over SMTP (e.g. your own Gmail with an app password, sending to yourself)."""

import asyncio
import smtplib
from email.message import EmailMessage


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
