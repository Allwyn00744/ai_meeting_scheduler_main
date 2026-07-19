"""
Pydantic schemas for Meeting Intelligence V3 — AI Action Item
Extraction.

Distinct from app/schemas/ai.py's ActionItem / GeneratedMeetingSummary
and app/schemas/meeting_intelligence.py's ActionItemResponse, which
both back the older AI Meeting Intelligence pipeline's action items
(meeting_action_items, keyed off meeting_summaries.id). This module's
schemas back the Meeting-Notes-V1-sourced action item flow (POST/GET
/meeting-intelligence/action-items/{id}) and persist to a dedicated
table, meeting_owner_action_items, keyed off meeting_owner_notes.id.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

PriorityLevel = Literal["Low", "Medium", "High"]
ActionItemStatusValue = Literal["Pending", "Completed"]

DEFAULT_PRIORITY: PriorityLevel = "Medium"
DEFAULT_STATUS: ActionItemStatusValue = "Pending"


class GeneratedActionItem(BaseModel):
    """One action item as produced directly by Gemini output."""

    task: Annotated[str, Field(min_length=1)]
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[PriorityLevel] = None

    @field_validator("task")
    @classmethod
    def task_not_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("task must not be blank or whitespace-only.")
        return trimmed

    @field_validator("assignee")
    @classmethod
    def normalize_assignee(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None


class GeneratedActionItemList(BaseModel):
    """
    Validates Gemini's raw JSON response before persistence. Kept
    separate from MeetingOwnerActionItemResponse below, which
    represents the persisted record (it requires database-assigned
    fields raw Gemini output does not have).
    """

    action_items: list[GeneratedActionItem]


class ActionItemStatusUpdate(BaseModel):
    status: ActionItemStatusValue


class MeetingOwnerActionItemResponse(BaseModel):
    """Persisted AI action item. meeting_id is supplied by the service
    from the surrounding request context - the underlying
    MeetingOwnerActionItem row is keyed by meeting_note_id, not
    meeting_id directly (see app/models/meeting_owner_action_item.py).
    """

    id: int
    meeting_id: int
    meeting_note_id: int
    task: str
    assignee: Optional[str] = None
    due_date: Optional[date] = None
    priority: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
