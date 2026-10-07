"""Instance-wide settings, read from environment variables (prefix SLOTBOT_) or a .env file."""

from typing import Literal

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

    # How race triggers are scheduled: in-process timers (local dev) or Google Cloud Tasks.
    triggers: Literal["local", "cloudtasks"] = "local"
    cloud_tasks_queue: str = ""  # projects/<project>/locations/<region>/queues/<queue>
    public_url: str = "http://localhost:8000"  # base URL Cloud Tasks calls back
    job_token: str = ""  # shared secret expected in X-Job-Token on /jobs/*

    # Race timing.
    lead_minutes: int = 5  # wake up (and log in) this long before the booking window opens
    poll_start_seconds: int = 60  # start polling availability this long before opening
    poll_seconds: float = 1.0
    retry_for_seconds: int = 120  # keep retrying this long after opening, then give up

    local_sync_minutes: int = 60  # local mode only: how often to re-read calendars

    madrid_opens_at: str = "00:00"  # hour the D-6 slots open (scripts/probe_madrid_opening.py measures it)
    madrid_request_light: bool = True  # when the site asks "with floodlights?" (paid extra), answer yes
