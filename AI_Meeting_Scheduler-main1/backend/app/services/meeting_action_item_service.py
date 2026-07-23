"""
MeetingActionItemService — Meeting Intelligence V3: AI Action Item
Extraction.

Business flow: Meeting -> Meeting Note (V1, owner-authored) -> Gemini
-> structured action items -> database. Deliberately narrower than
AIMeetingService / MeetingIntelligenceService
(app/services/ai_meeting_service.py, meeting_intelligence_service.py):
it sources notes from the persisted MeetingNote
(app/models/meeting_note.py, table meeting_owner_notes) instead of
freeform request text, and it never touches summaries.

Persistence uses MeetingOwnerActionItem / meeting_owner_action_items
(app/models/meeting_owner_action_item.py) exclusively - a table owned
solely by this feature, keyed on meeting_note_id. This service never
reads or writes MeetingActionItem / meeting_action_items
(app/models/meeting_action_item.py) - those remain exclusively owned
by the older AI Meeting Intelligence pipeline (AIMeetingService /
MeetingIntelligenceService, routes /ai/meetings/{id}/summary and
/meetings/{id}/action-items), which this service does not call,
import, or otherwise depend on.

Gemini failure isolation: GeminiService is called and its output
validated *before* any repository write is attempted, so a Gemini
failure (or invalid output) never reaches the database and cannot
corrupt previously persisted action items.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote
from app.models.meeting_owner_action_item import MeetingOwnerActionItem
from app.models.user import User
from app.repositories.meeting_note_repository import MeetingNoteRepository
from app.repositories.meeting_owner_action_item_repository import (
    MeetingOwnerActionItemRepository,
)
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_action_item import (
    DEFAULT_PRIORITY,
    ActionItemStatusUpdate,
    GeneratedActionItemList,
    MeetingOwnerActionItemResponse,
)
from app.services.gemini_service import GeminiService

logger = logging.getLogger(__name__)


class MeetingActionItemService:

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
    def _get_note_by_id_or_404(
        db: Session, meeting_note_id: int
    ) -> MeetingNote:
        note = MeetingNoteRepository.get_by_id(db, meeting_note_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Note not found",
            )

        return note

    @staticmethod
    def _get_action_item_or_404(
        db: Session, action_item_id: int
    ) -> MeetingOwnerActionItem:
        item = MeetingOwnerActionItemRepository.get_by_id(
            db, action_item_id
        )

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action item not found",
            )

        return item

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
                    "to access action items."
                ),
            )

    @staticmethod
    def _resolve_meeting_for_action_item(
        db: Session,
        item: MeetingOwnerActionItem,
    ):
        note = MeetingActionItemService._get_note_by_id_or_404(
            db, item.meeting_note_id
        )
        meeting = MeetingActionItemService._get_meeting_or_404(
            db, note.meeting_id
        )
        return meeting

    # ------------------------------------------------------------------
    # Generate / regenerate
    # ------------------------------------------------------------------

    @staticmethod
    def generate_action_items(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> list[MeetingOwnerActionItemResponse]:
        meeting = MeetingActionItemService._get_meeting_or_404(
            db, meeting_id
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Only the meeting owner can generate action items"
                ),
            )

        note = MeetingActionItemService._get_note_or_404(db, meeting_id)

        if not note.content.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "The meeting note is empty. Add content before "
                    "generating action items."
                ),
            )

        start_str = meeting.start_time.strftime("%Y-%m-%d %H:%M UTC")
        end_str = meeting.end_time.strftime("%Y-%m-%d %H:%M UTC")

        prompt = (
            "You are a meeting assistant. Extract actionable follow-up "
            "tasks from the following meeting note.\n\n"
            f"Meeting: {meeting.title}\n"
            f"Date: {start_str} - {end_str}\n\n"
            "Note:\n"
            f"{note.content}\n\n"
            "Return ONLY a valid JSON object with this exact "
            "structure:\n"
            "{\n"
            '  "action_items": [\n'
            "    {\n"
            '      "task": "<short actionable task description>",\n'
            '      "assignee": "<person responsible, or null if '
            'unknown>",\n'
            '      "due_date": "<YYYY-MM-DD, or null if not '
            'mentioned>",\n'
            '      "priority": "<one of Low, Medium, High>"\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Base the action items ONLY on the provided note.\n"
            "- Do not hallucinate or invent any information.\n"
            "- If no actionable tasks exist, return an empty "
            '"action_items" array.\n'
            "- Return ONLY the JSON object, no markdown, no "
            "explanation."
        )

        # --- Call Gemini and validate output before any DB write ---
        raw = GeminiService.generate_json(prompt)

        try:
            generated = GeneratedActionItemList.model_validate(raw)
        except ValidationError as exc:
            logger.warning(
                "Gemini action item output failed validation. "
                "meeting_id=%s error_count=%s",
                meeting_id,
                exc.error_count(),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "AI service returned an invalid action item "
                    "response."
                ),
            )

        # --- Persist: replace this note's action items ---
        try:
            MeetingOwnerActionItemRepository.delete_by_meeting_note_id(
                db, note.id
            )
            rows = [
                MeetingOwnerActionItem(
                    meeting_note_id=note.id,
                    task=generated_item.task,
                    assignee=generated_item.assignee,
                    due_date=generated_item.due_date,
                    priority=generated_item.priority or DEFAULT_PRIORITY,
                )
                for generated_item in generated.action_items
            ]
            created = MeetingOwnerActionItemRepository.create_many(
                db, rows
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        for row in created:
            db.refresh(row)

        return [
            MeetingActionItemService._to_response(row, meeting_id)
            for row in created
        ]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def list_action_items(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> list[MeetingOwnerActionItemResponse]:
        meeting = MeetingActionItemService._get_meeting_or_404(
            db, meeting_id
        )

        MeetingActionItemService._authorize_owner_or_participant(
            db, meeting, current_user
        )

        note = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if note is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No action items found for this meeting.",
            )

        rows = MeetingOwnerActionItemRepository.get_by_meeting_note_id(
            db, note.id
        )

        return [
            MeetingActionItemService._to_response(row, meeting_id)
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Update status
    # ------------------------------------------------------------------

    @staticmethod
    def update_status(
        db: Session,
        action_item_id: int,
        payload: ActionItemStatusUpdate,
        current_user: User,
    ) -> MeetingOwnerActionItemResponse:
        item = MeetingActionItemService._get_action_item_or_404(
            db, action_item_id
        )
        meeting = MeetingActionItemService._resolve_meeting_for_action_item(
            db, item
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can update action items",
            )

        try:
            updated = MeetingOwnerActionItemRepository.update_status(
                db, item, payload.status
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(updated)

        return MeetingActionItemService._to_response(updated, meeting.id)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    def delete_action_item(
        db: Session,
        action_item_id: int,
        current_user: User,
    ) -> dict:
        item = MeetingActionItemService._get_action_item_or_404(
            db, action_item_id
        )
        meeting = MeetingActionItemService._resolve_meeting_for_action_item(
            db, item
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can delete action items",
            )

        try:
            MeetingOwnerActionItemRepository.delete(db, item)
            db.commit()
        except Exception:
            db.rollback()
            raise

        return {"message": "Action item deleted successfully"}

    # ------------------------------------------------------------------
    # Mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _to_response(
        item: MeetingOwnerActionItem,
        meeting_id: int,
    ) -> MeetingOwnerActionItemResponse:
        # MeetingOwnerActionItem is keyed by meeting_note_id, not
        # meeting_id - meeting_id is supplied from the surrounding
        # request context instead of the row itself.
        return MeetingOwnerActionItemResponse(
            id=item.id,
            meeting_id=meeting_id,
            meeting_note_id=item.meeting_note_id,
            task=item.task,
            assignee=item.assignee,
            due_date=item.due_date,
            priority=item.priority,
            status=item.status,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
