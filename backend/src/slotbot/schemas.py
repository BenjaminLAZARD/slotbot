"""API and configuration models (Pydantic). ProfileConfig is also what the UI form edits."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Flex(BaseModel):
    """How far from the requested start time a slot may begin."""

    before_minutes: int = Field(0, ge=0, le=720)
    after_minutes: int | None = Field(None, ge=0, le=720, description="null = any later slot")


class Titles(BaseModel):
    """Title fragments marking each stage. `candidate` is what you type in your calendar."""

    candidate: str = "Candidate Tennis"
    pending: str = "Pending Tennis"
    success: str = "Success - Tennis"
    failure: str = "Failure - Tennis"

    @model_validator(mode="after")
    def distinct(self) -> "Titles":
        values = [v.strip().lower() for v in (self.candidate, self.pending, self.success, self.failure)]
        if "" in values or len(set(values)) != 4:
            raise ValueError("the four titles must be non-empty and different")
        return self


class ProfileConfig(BaseModel):
    calendar_id: str = Field(min_length=3, description="Google Calendar ID shared with the bot")
    provider: str = "madrid-tennis"
    home: str = Field("", description="Fallback origin when an event has no location")
    max_bike_minutes: int = Field(30, ge=5, le=120)
    bike_kmh: float = Field(15, ge=5, le=40)
    weekday: Flex = Flex(before_minutes=0, after_minutes=None)
    weekend: Flex = Flex(before_minutes=120, after_minutes=120)
    titles: Titles = Titles()
    lookahead_days: int = Field(30, ge=7, le=90)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: ProfileConfig


class ProfileOut(ProfileIn):
    id: int
    has_credentials: bool


class CredentialsIn(BaseModel):
    values: dict[str, str]


class VenueOut(BaseModel):
    id: str
    name: str
    address: str
    minutes: int


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    title: str
    play_start: datetime
    opens_at: datetime
    trigger_at: datetime
    status: str
    result: dict[str, Any] | None
    attempts: list[dict[str, Any]]
    updated_at: datetime


class ProviderOut(BaseModel):
    key: str
    label: str
    credential_fields: list[str]


class MetaOut(BaseModel):
    service_account_email: str
    triggers: str
    providers: list[ProviderOut]
