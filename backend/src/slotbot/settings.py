"""Instance-wide settings, read from environment variables (prefix SLOTBOT_) or a .env file."""

from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SLOTBOT_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://slotbot:slotbot@localhost:5432/slotbot"
    # Fernet key encrypting each profile's booking-site credentials at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    secret_key: str
    # Path to a Google service-account JSON key, or the JSON itself. Empty = ambient credentials
    # (on Cloud Run: the service's own identity).
    google_service_account: str = ""
    # Shown to Nominatim (OpenStreetMap geocoder), whose usage policy asks for a contact.
    contact_email: str = ""

    # Sign-in with Google: OAuth client ID (APIs & Services > Credentials, type "Web application").
    # Empty = no sign-in, everything belongs to one local user: allowed only on localhost.
    google_client_id: str = ""
    # Invite list: Google accounts allowed to sign in, comma-separated. The first one is the instance
    # owner and inherits profiles created before sign-in existed.
    allowed_emails: str = ""

    # Email notifications. Preferred: Resend with a "Sending access" API key (can only send).
    # Without your own domain Resend only delivers to your Resend account's address.
    resend_api_key: str = ""
    email_from: str = "slotbot <onboarding@resend.dev>"
    # Alternative: SMTP (empty user = off). With Gmail this needs an app password, which also grants
    # access to your mailbox: prefer Resend.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # How race triggers are scheduled: in-process timers (local dev) or Google Cloud Tasks.
    triggers: Literal["local", "cloudtasks"] = "local"
    cloud_tasks_queue: str = ""  # projects/<project>/locations/<region>/queues/<queue>
    public_url: str = "http://localhost:8000"  # base URL Cloud Tasks calls back
    job_token: str = ""  # shared secret expected in X-Job-Token (or ?token=) on /jobs/*
    # Service account whose Google-signed token /jobs/* also requires (set once the service is public;
    # while it is private, Cloud Run checks those tokens itself).
    job_caller: str = ""
    # GCP project whose billing the budget kill switch may disable (empty = kill switch off).
    gcp_project: str = ""

    # Race timing.
    lead_minutes: int = 5  # wake up (and log in) this long before the booking window opens
    poll_start_seconds: int = 60  # start polling availability this long before opening
    poll_seconds: float = 1.0
    retry_for_seconds: int = 120  # keep retrying this long after opening, then give up

    local_sync_minutes: int = 60  # local mode only: how often to re-read calendars

    madrid_opens_at: str = "00:00"  # hour the D-6 slots open (scripts/probe_madrid_opening.py measures it)
    madrid_request_light: bool = False  # when the site asks "with floodlights?" (paid extra): no

    @property
    def invited(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    @model_validator(mode="after")
    def _sign_in_outside_localhost(self) -> Self:
        if not self.google_client_id and not self.public_url.startswith("http://localhost"):
            raise ValueError("SLOTBOT_GOOGLE_CLIENT_ID is required when the app is not on localhost")
        return self
