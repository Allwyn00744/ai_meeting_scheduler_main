from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.schemas.external_guest import (
    ExternalGuestResponse,
    normalize_external_guest_emails,
)


class MeetingCreate(BaseModel):
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    location: str | None = None
    resource_id: int | None = None
    external_guest_emails: list[EmailStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_time_order(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    @model_validator(mode="after")
    def normalize_external_guests(self):
        self.external_guest_emails = normalize_external_guest_emails(
            self.external_guest_emails
        )
        return self


class MeetingUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    status: str | None = None

    @model_validator(mode="after")
    def check_time_order(self):
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self


class MeetingResponse(BaseModel):
    id: int
    title: str
    description: str | None
    start_time: datetime
    end_time: datetime
    location: str | None
    status: str
    owner_id: int
    resource_id: int | None
    external_guests: list[ExternalGuestResponse] = Field(
        default_factory=list
    )

    # Zoom Meeting Integration V1 and Microsoft Teams Integration V1
    # only - Google/Outlook provider fields (google_event_id,
    # google_meet_link, outlook_event_id, etc.) are deliberately not
    # exposed here; that is a separate, pre-existing gap and out of
    # scope for this change.
    zoom_meeting_id: str | None = None
    zoom_join_url: str | None = None
    zoom_start_url: str | None = None
    teams_join_url: str | None = None

    model_config = ConfigDict(from_attributes=True)
