"""
MeetingFollowUpEmailService — Meeting Intelligence V4: AI Follow-up
Email Generation.

Business flow: Meeting -> Meeting Note (V1, owner-authored) -> Meeting
Summary (V2, required) -> Action Items (V3, optional) -> Gemini ->
professional follow-up email -> database. Deliberately narrower than
AIMeetingService (app/services/ai_meeting_service.py): it sources its
content from the persisted MeetingOwnerNoteSummary and
MeetingOwnerActionItem rows instead of freeform request text, and it
never sends the generated email - this feature generates content only.

Persistence uses MeetingOwnerFollowUpEmail / meeting_owner_followup_emails
(app/models/meeting_owner_followup_email.py) exclusively - a table
owned solely by this feature, keyed on meeting_note_id. This service
never reads or writes any table or route belonging to the older AI
Meeting Intelligence pipeline (AIMeetingService, route
/ai/meetings/{id}/follow-up), which this service does not call,
import, or otherwise depend on. It also never calls EmailService -
generation and persistence only, no sending.

Gemini failure isolation: GeminiService is called and its output
validated *before* any repository read/write for the follow-up email
row is attempted, so a Gemini failure (or invalid output) never
reaches the database and cannot corrupt a previously persisted email.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote
from app.models.user import User
from app.repositories.meeting_note_repository import MeetingNoteRepository
from app.repositories.meeting_owner_action_item_repository import (
    MeetingOwnerActionItemRepository,
)
from app.repositories.meeting_owner_followup_email_repository import (
    MeetingOwnerFollowUpEmailRepository,
)
from app.repositories.meeting_owner_note_summary_repository import (
    MeetingOwnerNoteSummaryRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_followup_email import (
    GeneratedFollowUpEmail,
    MeetingFollowUpEmailResponse,
)
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class MeetingFollowUpEmailService:

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
                    "to access this follow-up email."
                ),
            )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(meeting, summary_text: str, action_items: list) -> str:
        start_str = meeting.start_time.strftime("%Y-%m-%d %H:%M UTC")
        end_str = meeting.end_time.strftime("%Y-%m-%d %H:%M UTC")

        if action_items:
            lines = []
            for item in action_items:
                details = [item.task]
                if item.assignee:
                    details.append(f"Assignee: {item.assignee}")
                if item.due_date:
                    details.append(f"Due: {item.due_date.isoformat()}")
                if item.priority:
                    details.append(f"Priority: {item.priority}")
                lines.append("- " + " | ".join(details))
            action_items_block = (
                "Action items:\n" + "\n".join(lines) + "\n\n"
            )
        else:
            action_items_block = (
                "Action items: none were recorded for this meeting.\n\n"
            )

        return (
            "You are a meeting assistant. Draft a professional "
            "follow-up email for the meeting below, based on its "
            "summary and action items.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} - {end_str}\n\n"
            "Meeting summary:\n"
            f"{summary_text}\n\n"
            f"{action_items_block}"
            "Return ONLY a valid JSON object with this exact "
            "structure:\n"
            "{\n"
            '  "subject": "<concise, professional email subject '
            'line>",\n'
            '  "body": "<professional email body addressed to the '
            "team, summarizing the meeting and listing action items "
            'if any>"\n'
            "}\n\n"
            "Rules:\n"
            "- Base the email ONLY on the provided summary and "
            "action items.\n"
            "- Do not hallucinate or invent any information.\n"
            "- Keep a professional, friendly tone.\n"
            "- Return ONLY the JSON object, no markdown, no "
            "explanation."
        )

    # ------------------------------------------------------------------
    # Generate / regenerate
    # ------------------------------------------------------------------

    @staticmethod
    def generate_followup_email(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingFollowUpEmailResponse:
        meeting = MeetingFollowUpEmailService._get_meeting_or_404(
            db, meeting_id
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only the meeting owner can generate a follow-up "
                    "email"
                ),
            )

        note = MeetingFollowUpEmailService._get_note_or_404(
            db, meeting_id
        )

        summary = MeetingOwnerNoteSummaryRepository.get_by_meeting_note_id(
            db, note.id
        )

        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No summary found for this meeting. Generate a "
                    "summary before drafting a follow-up email."
                ),
            )

        action_items = (
            MeetingOwnerActionItemRepository.get_by_meeting_note_id(
                db, note.id
            )
        )

        prompt = MeetingFollowUpEmailService._build_prompt(
            meeting, summary.summary, action_items
        )

        # --- Call Gemini and validate output before any DB write ---
        raw = GeminiService.generate_json(prompt)

        try:
            generated = GeneratedFollowUpEmail.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini follow-up email output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "AI service returned an invalid follow-up email "
                    "response."
                ),
            )

        # --- Persist: upsert this note's row in meeting_owner_followup_emails ---
        try:
            existing = (
                MeetingOwnerFollowUpEmailRepository.get_by_meeting_note_id(
                    db, note.id
                )
            )
            if existing is None:
                email_row = MeetingOwnerFollowUpEmailRepository.insert(
                    db,
                    note.id,
                    generated.subject,
                    generated.body,
                )
            else:
                email_row = MeetingOwnerFollowUpEmailRepository.update_email(
                    db,
                    existing,
                    generated.subject,
                    generated.body,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(email_row)

        return MeetingFollowUpEmailService._to_response(
            email_row, meeting_id
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_followup_email(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingFollowUpEmailResponse:
        meeting = MeetingFollowUpEmailService._get_meeting_or_404(
            db, meeting_id
        )

        MeetingFollowUpEmailService._authorize_owner_or_participant(
            db, meeting, current_user
        )

        note = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No follow-up email found for this meeting.",
            )

        email_row = (
            MeetingOwnerFollowUpEmailRepository.get_by_meeting_note_id(
                db, note.id
            )
        )

        if email_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No follow-up email found for this meeting.",
            )

        return MeetingFollowUpEmailService._to_response(
            email_row, meeting_id
        )

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        email_row,
        meeting_id: int,
    ) -> MeetingFollowUpEmailResponse:
        # MeetingOwnerFollowUpEmail is keyed by meeting_note_id, not
        # meeting_id - meeting_id is supplied from the surrounding
        # request context instead of the row itself.
        return MeetingFollowUpEmailResponse(
            id=email_row.id,
            meeting_id=meeting_id,
            subject=email_row.subject,
            body=email_row.body,
            created_at=email_row.created_at,
            updated_at=email_row.updated_at,
        )
