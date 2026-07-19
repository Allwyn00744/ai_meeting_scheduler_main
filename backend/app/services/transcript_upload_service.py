"""
TranscriptUploadService — Meeting Intelligence: AI Transcript Upload.

Business flow: uploaded transcript file -> extracted plain text ->
Meeting Note V1 (app/models/meeting_note.py, table meeting_owner_notes),
created if absent or overwritten if present. This is the sole entry
point that feeds a transcript into the existing pipeline - V2 (Summary)
through V5 (Insights) already read this same note via
MeetingNoteRepository.get_by_meeting_id, unchanged, exactly as they do
for an owner-typed note. No other table, service, or route is touched.

Must NOT:
  - Touch the legacy AI pipeline (AIMeetingService /
    MeetingIntelligenceService, meeting_notes / meeting_summaries /
    meeting_action_items tables).
  - Duplicate MeetingNoteService's create/update validation - content
    sanitization is reused directly from app.schemas.meeting_note.
"""
from __future__ import annotations

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote
from app.models.user import User
from app.repositories.meeting_note_repository import MeetingNoteRepository
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_note import _validate_note_content
from app.services.transcript_extraction_service import (
    SUPPORTED_EXTENSIONS,
    TranscriptExtractionService,
)

# Sole authoritative cap on the transcript FILE itself, enforced only by
# the bounded read loop below - mirrors POST /ai/schedule-voice in
# ai_routes.py. Request Content-Length is never inspected.
MAX_TRANSCRIPT_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

_UPLOAD_CHUNK_SIZE = 64 * 1024  # 64 KB


class TranscriptUploadService:

    @staticmethod
    async def _read_bounded(file: UploadFile) -> bytes:
        chunks: list[bytes] = []
        total_bytes = 0
        try:
            while True:
                chunk = await file.read(_UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_TRANSCRIPT_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            "Transcript file too large (max "
                            f"{MAX_TRANSCRIPT_UPLOAD_BYTES // (1024 * 1024)} "
                            "MB)."
                        ),
                    )
                chunks.append(chunk)
        finally:
            await file.close()

        return b"".join(chunks)

    @staticmethod
    async def upload_transcript(
        db: Session,
        meeting_id: int,
        file: UploadFile,
        current_user: User,
    ) -> MeetingNote:
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can upload a transcript",
            )

        # The filename extension is the sole authority on supported
        # file types - the client-declared Content-Type (e.g. the
        # generic "application/octet-stream" many clients send for
        # arbitrary file uploads) is never trusted for this check. An
        # unsupported extension is rejected here regardless of what
        # Content-Type accompanied it; a supported extension is
        # accepted the same way regardless of Content-Type.
        extension = TranscriptExtractionService.get_extension(
            file.filename
        )
        if extension not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=(
                    f"Unsupported file type: {extension or 'unknown'!r}. "
                    "Supported types: .txt, .pdf, .docx."
                ),
            )

        content = await TranscriptUploadService._read_bounded(file)

        if not content:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded transcript file is empty.",
            )

        extracted_text = TranscriptExtractionService.extract_text(
            file.filename, content
        )

        try:
            sanitized_text = _validate_note_content(extracted_text)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The transcript contains no readable text after "
                    "extraction."
                ),
            )

        existing_note = MeetingNoteRepository.get_by_meeting_id(
            db, meeting_id
        )

        if existing_note is None:
            note = MeetingNote(
                meeting_id=meeting_id,
                content=sanitized_text,
                created_by_id=current_user.id,
            )
            return MeetingNoteRepository.create(db, note)

        existing_note.content = sanitized_text
        return MeetingNoteRepository.update(db, existing_note)
