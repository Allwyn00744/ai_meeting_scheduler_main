from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.meeting import MeetingResponse

MAX_SERIES_OCCURRENCES = 52

Cadence = Literal["daily", "weekly", "monthly"]


class MeetingSeriesCreate(BaseModel):
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    location: str | None = None
    resource_id: int | None = None
    external_guest_emails: list[EmailStr] = Field(default_factory=list)
    cadence: Cadence
    interval: int = Field(default=1, ge=1, le=30)
    occurrence_count: int = Field(ge=1, le=MAX_SERIES_OCCURRENCES)


class MeetingSeriesResponse(BaseModel):
    id: int
    owner_id: int
    title: str
    description: str | None
    location: str | None
    resource_id: int | None
    cadence: Cadence
    interval: int
    occurrence_count: int
    created_at: datetime
    meetings: list[MeetingResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SeriesUpdateFromRequest(BaseModel):
    """
    "Edit this and following": title/description/location/resource_id
    are applied as-is to every selected occurrence. A time change is
    a fixed shift (e.g. "move from 10am to 11am, going forward") -
    every selected occurrence's start/end move by the same delta,
    each keeping its own original date, rather than accepting an
    arbitrary new start_time/end_time per occurrence.
    """
    title: str | None = None
    description: str | None = None
    location: str | None = None
    resource_id: int | None = None
    time_shift_minutes: int | None = None
