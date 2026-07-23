from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote
from app.models.user import User
from app.repositories.meeting_note_repository import MeetingNoteRepository
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository
from app.schemas.meeting_note import MeetingNoteCreate, MeetingNoteUpdate


class MeetingNoteService:

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
    def create_note(
        db: Session,
        meeting_id: int,
        payload: MeetingNoteCreate,
        current_user: User,
    ) -> MeetingNote:
        meeting = MeetingNoteService._get_meeting_or_404(db, meeting_id)

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can create notes",
            )

        existing = MeetingNoteRepository.get_by_meeting_id(db, meeting_id)

        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "A note already exists for this meeting. "
                    "Use update instead."
                ),
            )

        note = MeetingNote(
            meeting_id=meeting_id,
            content=payload.content,
            created_by_id=current_user.id,
        )

        return MeetingNoteRepository.create(db, note)

    @staticmethod
    def get_note(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> MeetingNote:
        meeting = MeetingNoteService._get_meeting_or_404(db, meeting_id)

        is_owner = meeting.owner_id == current_user.id
        is_participant = (
            MeetingParticipantRepository.get_by_meeting_and_user(
                db, meeting_id, current_user.id,
            )
            is not None
        )

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You must be the meeting owner or a participant "
                    "to view this note."
                ),
            )

        return MeetingNoteService._get_note_or_404(db, meeting_id)

    @staticmethod
    def update_note(
        db: Session,
        meeting_id: int,
        payload: MeetingNoteUpdate,
        current_user: User,
    ) -> MeetingNote:
        meeting = MeetingNoteService._get_meeting_or_404(db, meeting_id)

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can update notes",
            )

        note = MeetingNoteService._get_note_or_404(db, meeting_id)

        note.content = payload.content

        return MeetingNoteRepository.update(db, note)

    @staticmethod
    def delete_note(
        db: Session,
        meeting_id: int,
        current_user: User,
    ) -> dict:
        meeting = MeetingNoteService._get_meeting_or_404(db, meeting_id)

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can delete notes",
            )

        note = MeetingNoteService._get_note_or_404(db, meeting_id)

        MeetingNoteRepository.delete(db, note)

        return {"message": "Note deleted successfully"}
