"""
Pydantic schemas for Meeting Intelligence V5 — AI Meeting Insights.

Distinct from app/schemas/ai.py and app/schemas/meeting_intelligence.py,
which back the older AI Meeting Intelligence pipeline. This module's
schemas back the Meeting-Notes-V1-and-Summary-V2-sourced insight flow
(POST/GET /meeting-intelligence/insights/{id}) and persist to a
dedicated table, meeting_owner_insights, keyed off
meeting_owner_notes.id.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OverallStatus = Literal["On Track", "At Risk", "Blocked"]


class GeneratedInsight(BaseModel):
    """
    Validates Gemini's raw JSON response before persistence. Kept
    separate from the persisted-record response schema below, which
    requires database-assigned fields raw Gemini output does not have.
    """

    key_points: list[Annotated[str, Field(min_length=1)]]
    decisions: list[Annotated[str, Field(min_length=1)]]
    risks: list[Annotated[str, Field(min_length=1)]]
    next_steps: list[Annotated[str, Field(min_length=1)]]
    overall_status: OverallStatus

    @model_validator(mode="after")
    def lists_not_blank(self) -> "GeneratedInsight":
        for field_name in ("key_points", "decisions", "risks", "next_steps"):
            values = getattr(self, field_name)
            if any(not value.strip() for value in values):
                raise ValueError(
                    f"{field_name} entries must not be blank or "
                    "whitespace-only."
                )
        return self


class MeetingOwnerInsightResponse(BaseModel):
    """Persisted AI insight, returned by both the generate/regenerate
    endpoint and the read endpoint. meeting_id is supplied by the
    service from the surrounding request context - the underlying
    MeetingOwnerInsight row is keyed by meeting_note_id, not meeting_id
    directly (see app/models/meeting_owner_insight.py).
    """

    id: int
    meeting_id: int
    key_points: list[str]
    decisions: list[str]
    risks: list[str]
    next_steps: list[str]
    overall_status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
