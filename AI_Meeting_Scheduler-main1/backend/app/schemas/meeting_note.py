"""
Pydantic schemas for Meeting Notes V1 (manually authored, owner-written
notes). Separate from app.schemas.meeting_intelligence.MeetingNotesResponse,
which represents AI transcript/summary-pipeline content.
"""
import html
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


def _validate_note_content(value: str) -> str:
    """
    Shared by MeetingNoteCreate and MeetingNoteUpdate: trims
    surrounding whitespace, rejects an empty/whitespace-only note, and
    escapes HTML so stored/returned content can never execute as
    markup or script in a browser that renders it unescaped.
    """
    trimmed = value.strip()

    if not trimmed:
        raise ValueError("Note content must not be empty.")

    return html.escape(trimmed)


class MeetingNoteCreate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _validate_note_content(value)


class MeetingNoteUpdate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        return _validate_note_content(value)


class MeetingNoteResponse(BaseModel):
    id: int
    meeting_id: int
    content: str
    created_by_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
