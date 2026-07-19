"""
Pydantic schemas for Meeting Intelligence V2 — AI Meeting Summary.

Distinct from app/schemas/ai.py's GeneratedMeetingSummary /
MeetingSummaryResponse, which back the freeform-notes summary +
action-item extraction flow (POST /ai/meetings/{id}/summary). This
module's schemas back the Meeting-Notes-V1-sourced summary flow
(POST/GET /meeting-intelligence/summary/{id}) and intentionally carry
no action_items — that concept is out of scope for this feature.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GeneratedNoteSummary(BaseModel):
    """
    Validates Gemini's raw JSON response before persistence. Kept
    separate from the persisted-record response schema below, which
    requires database-assigned fields raw Gemini output does not have.
    """

    summary: Annotated[str, Field(min_length=1)]

    @model_validator(mode="after")
    def summary_not_blank(self) -> "GeneratedNoteSummary":
        if not self.summary.strip():
            raise ValueError("summary must not be blank or whitespace-only.")
        return self


class MeetingAISummaryResponse(BaseModel):
    """Persisted AI summary, returned by both the generate/regenerate
    endpoint and the read endpoint. meeting_id is supplied by the
    service from the surrounding request context - the underlying
    MeetingOwnerNoteSummary row is keyed by meeting_note_id, not
    meeting_id directly (see app/models/meeting_owner_note_summary.py).
    """

    id: int
    meeting_id: int
    summary: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
