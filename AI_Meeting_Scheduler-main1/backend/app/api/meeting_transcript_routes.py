"""
Meeting Intelligence — AI Transcript Upload. Extracts plain text from
an uploaded transcript file and writes it into the meeting's Meeting
Note V1 (app/api/meeting_note_routes.py), creating it if absent or
overwriting it if present. This is the sole entry point that feeds a
transcript into the existing V1-V5 Meeting Intelligence pipeline; V2
(Summary) through V5 (Insights) read the resulting note unchanged via
MeetingNoteRepository, exactly as they do for an owner-typed note.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_note import MeetingNoteResponse
from app.services.transcript_upload_service import TranscriptUploadService

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Transcript"],
)


@router.post(
    "/transcript/{meeting_id}",
    response_model=MeetingNoteResponse,
    status_code=200,
)
async def upload_transcript(
    meeting_id: int,
    file: UploadFile = File(
        ...,
        description=(
            "Meeting transcript file. Supported types: .txt, .pdf, "
            ".docx (max 5 MB). Scanned/image-only PDFs are not "
            "supported."
        ),
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await TranscriptUploadService.upload_transcript(
        db,
        meeting_id,
        file,
        current_user,
    )
