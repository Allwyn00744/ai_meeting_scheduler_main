"""
MeetingInsightService — Meeting Intelligence V5: AI Meeting Insights.

Business flow: Meeting -> Meeting Note (V1, owner-authored) -> Meeting
Summary (V2, required) -> Action Items (V3, optional) -> Follow-up
Email (V4, optional) -> Gemini -> structured insights (key points,
decisions, risks, next steps, overall status) -> database. Deliberately
narrower than AIMeetingService (app/services/ai_meeting_service.py): it
sources its content from the persisted MeetingOwnerNoteSummary,
MeetingOwnerActionItem, and MeetingOwnerFollowUpEmail rows instead of
freeform request text.

Persistence uses MeetingOwnerInsight / meeting_owner_insights
(app/models/meeting_owner_insight.py) exclusively - a table owned
solely by this feature, keyed on meeting_note_id. This service never
reads or writes any table or route belonging to the older AI Meeting
Intelligence pipeline (AIMeetingService, MeetingIntelligenceService),
which this service does not call, import, or otherwise depend on.

Gemini failure isolation: GeminiService is called and its output
validated *before* any repository read/write for the insight row is
attempted, so a Gemini failure (or invalid output) never reaches the
database and cannot corrupt a previously persisted insight.
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
from app.repositories.meeting_owner_insight_repository import (
    MeetingOwnerInsightRepository,
)
from app.repositories.meeting_owner_note_summary_repository import (
    MeetingOwnerNoteSummaryRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_insight import (
    GeneratedInsight,
    MeetingOwnerInsightResponse,
)
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class MeetingInsightService:

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
                    "to access these insights."
                ),
            )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(
        meeting,
        summary_text: str,
        action_items: list,
        followup_email,
    ) -> str:
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

        if followup_email is not None:
            followup_block = (
                "Follow-up email already drafted:\n"
                f"Subject: {followup_email.subject}\n"
                f"{followup_email.body}\n\n"
            )
        else:
            followup_block = (
                "Follow-up email: none has been drafted for this "
                "meeting.\n\n"
            )

        return (
            "You are a meeting assistant. Analyse the meeting below "
            "and produce structured insights based on its summary, "
            "action items, and follow-up email.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} - {end_str}\n\n"
            "Meeting summary:\n"
            f"{summary_text}\n\n"
            f"{action_items_block}"
            f"{followup_block}"
            "Return ONLY a valid JSON object with this exact "
            "structure:\n"
            "{\n"
            '  "key_points": ["...", "..."],\n'
            '  "decisions": ["...", "..."],\n'
            '  "risks": ["...", "..."],\n'
            '  "next_steps": ["...", "..."],\n'
            '  "overall_status": "On Track"\n'
            "}\n\n"
            "Rules:\n"
            "- Base the insights ONLY on the provided summary, action "
            "items, and follow-up email.\n"
            "- Do not hallucinate or invent any information.\n"
            "- overall_status must be exactly one of: \"On Track\", "
            '"At Risk", "Blocked".\n'
            "- If a list has no items, return an empty array for it.\n"
            "- Return ONLY the JSON object, no markdown, no "
            "explanation."
        )

    # ------------------------------------------------------------------
    # Generate / regenerate
    # ------------------------------------------------------------------

    @staticmethod
    def generate_insight(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingOwnerInsightResponse:
        meeting = MeetingInsightService._get_meeting_or_404(
            db, meeting_id
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can generate insights",
            )

        note = MeetingInsightService._get_note_or_404(db, meeting_id)

        summary = MeetingOwnerNoteSummaryRepository.get_by_meeting_note_id(
            db, note.id
        )

        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No summary found for this meeting. Generate a "
                    "summary before generating insights."
                ),
            )

        action_items = (
            MeetingOwnerActionItemRepository.get_by_meeting_note_id(
                db, note.id
            )
        )

        followup_email = (
            MeetingOwnerFollowUpEmailRepository.get_by_meeting_note_id(
                db, note.id
            )
        )

        prompt = MeetingInsightService._build_prompt(
            meeting, summary.summary, action_items, followup_email
        )

        # --- Call Gemini and validate output before any DB write ---
        raw = GeminiService.generate_json(prompt)

        try:
            generated = GeneratedInsight.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini insight output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI service returned an invalid insight response.",
            )

        # --- Persist: upsert this note's row in meeting_owner_insights ---
        try:
            existing = MeetingOwnerInsightRepository.get_by_meeting_note_id(
                db, note.id
            )
            if existing is None:
                insight_row = MeetingOwnerInsightRepository.insert(
                    db,
                    note.id,
                    generated.key_points,
                    generated.decisions,
                    generated.risks,
                    generated.next_steps,
                    generated.overall_status,
                )
            else:
                insight_row = MeetingOwnerInsightRepository.update_insight(
                    db,
                    existing,
                    generated.key_points,
                    generated.decisions,
                    generated.risks,
                    generated.next_steps,
                    generated.overall_status,
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(insight_row)

        return MeetingInsightService._to_response(insight_row, meeting_id)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_insight(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingOwnerInsightResponse:
        meeting = MeetingInsightService._get_meeting_or_404(
            db, meeting_id
        )

        MeetingInsightService._authorize_owner_or_participant(
            db, meeting, current_user
        )

        note = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No insights found for this meeting.",
            )

        insight_row = MeetingOwnerInsightRepository.get_by_meeting_note_id(
            db, note.id
        )

        if insight_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No insights found for this meeting.",
            )

        return MeetingInsightService._to_response(insight_row, meeting_id)

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        insight_row,
        meeting_id: int,
    ) -> MeetingOwnerInsightResponse:
        # MeetingOwnerInsight is keyed by meeting_note_id, not
        # meeting_id - meeting_id is supplied from the surrounding
        # request context instead of the row itself.
        return MeetingOwnerInsightResponse(
            id=insight_row.id,
            meeting_id=meeting_id,
            key_points=insight_row.key_points_json,
            decisions=insight_row.decisions_json,
            risks=insight_row.risks_json,
            next_steps=insight_row.next_steps_json,
            overall_status=insight_row.overall_status,
            created_at=insight_row.created_at,
            updated_at=insight_row.updated_at,
        )
