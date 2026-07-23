"""
MeetingIntelligenceService — persistence for meeting notes, AI-generated
summaries, and action items.

Authorization: this service implements its own owner-or-participant
check using MeetingRepository and MeetingParticipantRepository. It does
NOT import or call AIMeetingService._get_meeting_authorized — the two
checks are intentionally independent, duplicated implementations of the
same semantics.

Transaction ownership: MeetingNotesRepository, MeetingSummaryRepository,
and MeetingActionItemRepository never call db.commit() or db.rollback().
This service owns every write transaction: exactly one db.commit() on
success, db.rollback() + re-raise on any failure. No partially updated
intelligence state (e.g. old action items deleted but new ones not yet
created) is ever committed or made visible.
"""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.meeting_action_item import MeetingActionItem
from app.models.user import User
from app.repositories.meeting_action_item_repository import (
    MeetingActionItemRepository,
)
from app.repositories.meeting_notes_repository import MeetingNotesRepository
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.meeting_summary_repository import (
    MeetingSummaryRepository,
)
from app.schemas.ai import ActionItem, MeetingSummaryResponse
from app.schemas.meeting_intelligence import (
    ActionItemResponse,
    ActionItemStatus,
    MeetingNotesResponse,
)


class MeetingIntelligenceService:

    # ------------------------------------------------------------------
    # Authorization (independent duplicate of AIMeetingService's check)
    # ------------------------------------------------------------------

    @staticmethod
    def _authorize_owner_or_participant(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found.",
            )

        is_owner = meeting.owner_id == current_user.id
        is_participant = (
            MeetingParticipantRepository.get_by_meeting_and_user(
                db, meeting_id, current_user.id
            )
            is not None
        )

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorised to access this meeting.",
            )

        return meeting

    # ------------------------------------------------------------------
    # Persistence: generate/regenerate summary + notes + action items
    # ------------------------------------------------------------------

    @staticmethod
    def persist_summary(
        db: Session,
        meeting_id: int,
        notes_text: str,
        summary_text: str,
        action_items: list[ActionItem],
        current_user: User,
    ) -> MeetingSummaryResponse:
        """
        Upserts meeting_notes, upserts meeting_summaries, deletes the
        existing meeting_action_items for this meeting, and creates the
        replacement set — all inside a single uncommitted transaction,
        followed by exactly one db.commit(). On any failure the entire
        transaction is rolled back and the exception is re-raised, so
        previously committed notes/summary/action items are preserved
        unchanged.
        """
        MeetingIntelligenceService._authorize_owner_or_participant(
            db, meeting_id, current_user
        )

        try:
            existing_notes = MeetingNotesRepository.get_by_meeting_id(
                db, meeting_id
            )
            if existing_notes is None:
                notes_row = MeetingNotesRepository.insert(
                    db, meeting_id, notes_text, current_user.id
                )
            else:
                notes_row = MeetingNotesRepository.update_content(
                    db, existing_notes, notes_text
                )

            existing_summary = MeetingSummaryRepository.get_by_meeting_id(
                db, meeting_id
            )
            if existing_summary is None:
                summary_row = MeetingSummaryRepository.insert(
                    db,
                    meeting_id,
                    summary_text,
                    notes_row.id,
                    current_user.id,
                )
            else:
                summary_row = MeetingSummaryRepository.update_summary(
                    db,
                    existing_summary,
                    summary_text,
                    notes_row.id,
                    current_user.id,
                )

            # Delete + recreate within the same uncommitted transaction.
            # The delete is flushed but not committed here — if any
            # later step fails, the rollback below restores the
            # previously committed action items.
            MeetingActionItemRepository.delete_by_meeting_id(
                db, meeting_id
            )

            new_items = MeetingActionItemRepository.create_many(
                db,
                [
                    MeetingActionItem(
                        meeting_id=meeting_id,
                        summary_id=summary_row.id,
                        task=item.task,
                        assignee=item.assignee,
                        due_date=item.due_date,
                        status="pending",
                    )
                    for item in action_items
                ],
            )

            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(notes_row)
        db.refresh(summary_row)
        for db_item in new_items:
            db.refresh(db_item)

        return MeetingSummaryResponse(
            id=summary_row.id,
            meeting_id=summary_row.meeting_id,
            summary=summary_row.summary_text,
            action_items=[
                ActionItemResponse.model_validate(db_item)
                for db_item in new_items
            ],
            created_at=summary_row.created_at,
            updated_at=summary_row.updated_at,
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    @staticmethod
    def get_notes(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingNotesResponse:
        MeetingIntelligenceService._authorize_owner_or_participant(
            db, meeting_id, current_user
        )

        notes = MeetingNotesRepository.get_by_meeting_id(db, meeting_id)

        if notes is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No notes found for this meeting.",
            )

        return MeetingNotesResponse.model_validate(notes)

    @staticmethod
    def get_summary(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingSummaryResponse:
        MeetingIntelligenceService._authorize_owner_or_participant(
            db, meeting_id, current_user
        )

        summary = MeetingSummaryRepository.get_by_meeting_id(
            db, meeting_id
        )

        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No summary found for this meeting.",
            )

        items = MeetingActionItemRepository.get_by_meeting_id(
            db, meeting_id
        )

        return MeetingSummaryResponse(
            id=summary.id,
            meeting_id=summary.meeting_id,
            summary=summary.summary_text,
            action_items=[
                ActionItemResponse.model_validate(item) for item in items
            ],
            created_at=summary.created_at,
            updated_at=summary.updated_at,
        )

    @staticmethod
    def get_action_items(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> list[ActionItemResponse]:
        MeetingIntelligenceService._authorize_owner_or_participant(
            db, meeting_id, current_user
        )

        items = MeetingActionItemRepository.get_by_meeting_id(
            db, meeting_id
        )

        return [ActionItemResponse.model_validate(item) for item in items]

    # ------------------------------------------------------------------
    # Action item status update
    # ------------------------------------------------------------------

    @staticmethod
    def update_action_item_status(
        db: Session,
        action_item_id: int,
        new_status: ActionItemStatus,
        current_user: User,
    ) -> ActionItemResponse:
        item = MeetingActionItemRepository.get_by_id(db, action_item_id)

        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Action item not found.",
            )

        MeetingIntelligenceService._authorize_owner_or_participant(
            db, item.meeting_id, current_user
        )

        try:
            MeetingActionItemRepository.update_status(
                db, item, new_status
            )
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(item)

        return ActionItemResponse.model_validate(item)
