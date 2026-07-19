"""
Pydantic schemas for AI endpoints.

All AI output must be validated by these schemas before being passed
to any application service. These schemas never directly touch the
database.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

# Import the authoritative bounds from the existing scheduler schema so
# that the AI layer never diverges from them.
from app.schemas.scheduler import MAX_OCCURRENCES, SUPPORTED_REPEAT_TYPES
from app.schemas.meeting_intelligence import ActionItemResponse
from app.schemas.external_guest import normalize_external_guest_emails

# ---------------------------------------------------------------------------
# Field-level limits
# ---------------------------------------------------------------------------

# Maximum character lengths for free-text inputs. Public (no leading
# underscore) because AIMeetingService.schedule_from_voice also enforces
# this same bound against a Gemini-produced transcript, which never
# passes through TextScheduleRequest's own Pydantic validation.
MAX_SCHEDULING_TEXT_LENGTH = 2_000  # scheduling request
_MAX_NOTES_LEN = 50_000              # meeting notes / transcript

# Duration bounds (minutes).
_MIN_DURATION = 1
_MAX_DURATION = 1_440       # 24 hours


# ---------------------------------------------------------------------------
# AI TEXT SCHEDULING
# ---------------------------------------------------------------------------


class TextScheduleRequest(BaseModel):
    """Request body for POST /ai/schedule-text."""

    text: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_SCHEDULING_TEXT_LENGTH,
            description="Natural-language scheduling request.",
        ),
    ]

    @model_validator(mode="after")
    def text_not_blank(self) -> "TextScheduleRequest":
        if not self.text.strip():
            raise ValueError("text must not be blank or whitespace-only.")
        return self


class AISchedulingIntent(BaseModel):
    """
    Validated intermediate produced from Gemini output.

    This schema NEVER writes to the database directly — it is converted
    into a ScheduleMeetingRequest before being passed to SchedulerService.

    All datetime fields must be timezone-aware; naive datetimes from
    Gemini are rejected to prevent silent UTC/local mismatches.
    """

    title: Annotated[
        str,
        Field(min_length=1, description="Meeting title."),
    ]
    description: Optional[str] = None
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_minutes: Optional[
        Annotated[int, Field(ge=_MIN_DURATION, le=_MAX_DURATION)]
    ] = None
    location: Optional[str] = None
    participant_ids: list[
        Annotated[int, Field(gt=0, description="Must be a positive user ID.")]
    ] = Field(default_factory=list)
    external_guest_emails: list[EmailStr] = Field(
        default_factory=list,
        description=(
            "Email addresses extracted from the request text. Not yet "
            "classified as registered-user vs. external guest - "
            "AIMeetingService resolves that authoritatively against "
            "the users table."
        ),
    )
    repeat: bool = False
    repeat_type: Optional[str] = None
    occurrences: Optional[
        Annotated[int, Field(ge=1, le=MAX_OCCURRENCES)]
    ] = None

    @model_validator(mode="after")
    def validate_intent(self) -> "AISchedulingIntent":
        # --- Title must not be blank ---
        if not self.title.strip():
            raise ValueError("title must not be blank or whitespace-only.")

        # --- Reject timezone-naive datetimes ---
        if self.start_time.tzinfo is None:
            raise ValueError(
                "start_time must be timezone-aware. "
                "Gemini must return an ISO 8601 UTC datetime "
                "(e.g. 2026-07-09T16:00:00Z)."
            )
        if self.end_time is not None and self.end_time.tzinfo is None:
            raise ValueError(
                "end_time must be timezone-aware. "
                "Gemini must return an ISO 8601 UTC datetime "
                "(e.g. 2026-07-09T17:00:00Z)."
            )

        # --- Derive end_time from duration_minutes when absent ---
        if self.end_time is None:
            if self.duration_minutes is not None:
                self.end_time = self.start_time + timedelta(
                    minutes=self.duration_minutes
                )
            else:
                raise ValueError(
                    "AI output must provide either end_time or "
                    "duration_minutes."
                )

        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time.")

        # --- repeat_type must be a supported value ---
        if self.repeat_type is not None:
            if self.repeat_type not in SUPPORTED_REPEAT_TYPES:
                raise ValueError(
                    f"repeat_type must be one of "
                    f"{sorted(SUPPORTED_REPEAT_TYPES)}, got "
                    f"'{self.repeat_type}'."
                )

        # --- repeat/repeat_type/occurrences consistency ---
        if self.repeat:
            if self.repeat_type is None:
                raise ValueError(
                    "repeat_type is required when repeat is true."
                )
            if self.occurrences is None:
                raise ValueError(
                    "occurrences is required when repeat is true."
                )
        else:
            # When repeat is False, clear any leftover recurrence fields
            # that Gemini may have spuriously populated.
            self.repeat_type = None
            self.occurrences = None

        # --- Participant IDs must be unique ---
        if len(self.participant_ids) != len(set(self.participant_ids)):
            raise ValueError("participant_ids must not contain duplicates.")

        # --- Normalize + dedupe extracted emails (case-insensitive) ---
        self.external_guest_emails = normalize_external_guest_emails(
            self.external_guest_emails
        )

        return self


# ---------------------------------------------------------------------------
# MEETING SUMMARY + ACTION ITEMS
# ---------------------------------------------------------------------------


class MeetingNotesRequest(BaseModel):
    """Request body shared by the summary and follow-up endpoints."""

    notes: Annotated[
        str,
        Field(
            min_length=1,
            max_length=_MAX_NOTES_LEN,
            description="Meeting notes or transcript text.",
        ),
    ]

    @model_validator(mode="after")
    def notes_not_blank(self) -> "MeetingNotesRequest":
        if not self.notes.strip():
            raise ValueError("notes must not be blank or whitespace-only.")
        return self


class ActionItem(BaseModel):
    """Raw action item shape as produced directly by Gemini output."""

    task: str
    assignee: Optional[str] = None
    due_date: Optional[date] = None


class GeneratedMeetingSummary(BaseModel):
    """
    Validates Gemini's raw JSON response for the summary endpoint,
    before persistence. This is intentionally separate from
    MeetingSummaryResponse, which represents the persisted record
    (it requires database-assigned fields like id/meeting_id that
    raw Gemini output does not have).
    """

    summary: str
    action_items: list[ActionItem]


class MeetingSummaryResponse(BaseModel):
    """
    Persisted meeting summary, returned by both the generation
    endpoint (POST /ai/meetings/{id}/summary) and the read endpoint
    (GET /meetings/{id}/summary). `summary` and `action_items[].task/
    .assignee/.due_date` are the original response fields; the rest
    are additive persistence metadata.
    """

    id: int
    meeting_id: int
    summary: str
    action_items: list[ActionItemResponse]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# FOLLOW-UP GENERATION
# ---------------------------------------------------------------------------


class FollowUpDraftResponse(BaseModel):
    email_subject: str
    email_body: str

    model_config = ConfigDict(from_attributes=True)
