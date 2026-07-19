"""
Pydantic schemas for Meeting Intelligence V4 — AI Follow-up Email
Generation.

Distinct from app/schemas/ai.py's MeetingNotesRequest /
FollowUpDraftResponse, which back the older AI Meeting Intelligence
pipeline's follow-up draft (POST /ai/meetings/{id}/follow-up, freeform
notes text, never persisted). This module's schemas back the
Meeting-Notes-V1-and-Summary-V2-sourced follow-up flow (POST/GET
/meeting-intelligence/follow-up/{id}) and persist to a dedicated
table, meeting_owner_followup_emails, keyed off meeting_owner_notes.id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeneratedFollowUpEmail(BaseModel):
    """
    Validates Gemini's raw JSON response before persistence. Kept
    separate from the persisted-record response schema below, which
    requires database-assigned fields raw Gemini output does not have.
    """

    subject: Annotated[str, Field(min_length=1)]
    body: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def fields_not_blank(self) -> "GeneratedFollowUpEmail":
        if not self.subject.strip():
            raise ValueError("subject must not be blank or whitespace-only.")
        if not self.body.strip():
            raise ValueError("body must not be blank or whitespace-only.")
        return self


class MeetingFollowUpEmailResponse(BaseModel):
    """Persisted AI follow-up email, returned by both the
    generate/regenerate endpoint and the read endpoint. meeting_id is
    supplied by the service from the surrounding request context - the
    underlying MeetingOwnerFollowUpEmail row is keyed by
    meeting_note_id, not meeting_id directly (see
    app/models/meeting_owner_followup_email.py).
    """

    id: int
    meeting_id: int
    subject: str
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
