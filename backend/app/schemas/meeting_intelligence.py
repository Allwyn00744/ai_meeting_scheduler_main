"""
Pydantic schemas for persisted meeting intelligence records (notes,
summaries, action items).

These are separate from app.schemas.ai, which validates raw AI I/O.
ActionItemResponse is a superset of app.schemas.ai.ActionItem — it adds
persistence metadata (id, meeting_id, status, timestamps) without
removing or renaming any existing field.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

ActionItemStatus = Literal["pending", "completed"]


class MeetingNotesResponse(BaseModel):
    id: int
    meeting_id: int
    content: str
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActionItemResponse(BaseModel):
    id: int
    meeting_id: int
    task: str
    assignee: str | None = None
    due_date: date | None = None
    status: ActionItemStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ActionItemStatusUpdate(BaseModel):
    status: ActionItemStatus
