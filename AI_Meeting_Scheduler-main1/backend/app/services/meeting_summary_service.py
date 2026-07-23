"""
MeetingSummaryService — Meeting Intelligence V2: AI Meeting Summary.

Business flow: Meeting -> Meeting Note (V1, owner-authored) -> Gemini
-> AI Summary. This is deliberately narrower than AIMeetingService /
MeetingIntelligenceService (app/services/ai_meeting_service.py,
meeting_intelligence_service.py): it sources notes from the persisted
MeetingNote (app/models/meeting_note.py, table meeting_owner_notes)
instead of freeform request text, and it never touches action items.

Persistence uses MeetingOwnerNoteSummary / meeting_owner_note_summaries
(app/models/meeting_owner_note_summary.py) exclusively - a table owned
solely by this feature, keyed on meeting_note_id. This service never
reads or writes MeetingSummary / meeting_summaries
(app/models/meeting_summary.py) or meeting_action_items - those remain
exclusively owned by the older AI Meeting Intelligence pipeline
(AIMeetingService / MeetingIntelligenceService, routes
/ai/meetings/{id}/summary and /meetings/{id}/summary), which this
service does not call, import, or otherwise depend on.

Gemini failure isolation: GeminiService is called and its output
validated *before* any repository read/write for the summary row is
attempted, so a Gemini failure (or invalid output) never reaches the
database and cannot corrupt a previously persisted summary.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote
from app.models.user import User
from app.repositories.meeting_note_repository import MeetingNoteRepository
from app.repositories.meeting_owner_note_summary_repository import (
    MeetingOwnerNoteSummaryRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_summary import (
    GeneratedNoteSummary,
    MeetingAISummaryResponse,
)
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class MeetingSummaryService:

    # ------------------------------------------------------------------
    # Authorization / lookups
    # ------------------------------------------------------------------

    @staticmethod
    def _get_meeting_or_404(db: Session, meeting_id: int):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        return meeting

    @staticmethod
    def _get_note_or_404(db: Session, meeting_id: int) -> MeetingNote:
        note = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )

        return note

    @staticmethod
    def _authorize_owner_or_participant(
        db: Session,
        meeting,
        current_user: User,
    ) -> None:
        is_owner = meeting.owner_id == current_user.id
        is_participant = (
            MeetingParticipantRepository.get_by_meeting_and_user(
                db, meeting.id, current_user.id,
            )
            is not None
        )

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You must be the meeting owner or a participant "
                    "to access this summary."
                ),
            )

    # ------------------------------------------------------------------
    # Generate / regenerate
    # ------------------------------------------------------------------

    @staticmethod
    def generate_summary(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingAISummaryResponse:
        meeting = MeetingSummaryService._get_meeting_or_404(db, meeting_id)

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can generate a summary",
            )

        note = MeetingSummaryService._get_note_or_404(db, meeting_id)

        if not note.content.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The meeting note is empty. Add content before "
                    "generating a summary."
                ),
            )

        start_str = meeting.start_time.strftime("%Y-%m-%d %H:%M UTC")
        end_str = meeting.end_time.strftime("%Y-%m-%d %H:%M UTC")

        prompt = (
            "You are a meeting assistant. Summarise the following "
            "meeting note.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} - {end_str}\n\n"
            "Note:\n"
            f"{note.content}\n\n"
            "Return ONLY a valid JSON object with this exact structure:\n"
            "{\n"
            '  "summary": "<concise 2-4 sentence summary>"\n'
            "}\n\n"
            "Rules:\n"
            "- Base the summary ONLY on the provided note.\n"
            "- Do not hallucinate or invent any information.\n"
            "- Keep the summary factual and concise.\n"
            "- Return ONLY the JSON object, no markdown, no explanation."
        )

        # --- Call Gemini and validate output before any DB write ---
        raw = GeminiService.generate_json(prompt)

        try:
            generated = GeneratedNoteSummary.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini summary output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned an invalid summary response.",
            )

        # --- Persist: upsert this note's row in meeting_owner_note_summaries ---
        try:
            existing = MeetingOwnerNoteSummaryRepository.get_by_meeting_note_id(
                db, note.id
            )
            if existing is None:
                summary_row = MeetingOwnerNoteSummaryRepository.insert(
                    db,
                    note.id,
                    generated.summary,
                )
            else:
                summary_row = MeetingOwnerNoteSummaryRepository.update_summary(
                    db,
                    existing,
                    generated.summary,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(summary_row)

        return MeetingSummaryService._to_response(summary_row, meeting_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_summary(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingAISummaryResponse:
        meeting = MeetingSummaryService._get_meeting_or_404(db, meeting_id)

        MeetingSummaryService._authorize_owner_or_participant(
            db, meeting, current_user
        )

        note = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No summary found for this meeting.",
            )

        summary = MeetingOwnerNoteSummaryRepository.get_by_meeting_note_id(
            db, note.id
        )

        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No summary found for this meeting.",
            )

        return MeetingSummaryService._to_response(summary, meeting_id)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        summary,
        meeting_id: int,
    ) -> MeetingAISummaryResponse:
        # MeetingOwnerNoteSummary is keyed by meeting_note_id, not
        # meeting_id - meeting_id is supplied from the surrounding
        # request context instead of the row itself.
        return MeetingAISummaryResponse(
            id=summary.id,
            meeting_id=meeting_id,
            summary=summary.summary,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )
