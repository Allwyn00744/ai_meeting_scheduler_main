from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.meeting_participant import MeetingParticipant
from app.models.user import User
from app.repositories.meeting_repository import MeetingRepository
from app.repositories.meeting_participant_repository import (
    MeetingParticipantRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.meeting_participant import (
    ParticipantCreate,
    ParticipantUpdate,
)


class MeetingParticipantService:

    @staticmethod
    def add_participant(
        db: Session,
        meeting_id: int,
        participant: ParticipantCreate,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can invite participants",
            )

        participant_user = UserRepository.get_user_by_id(
            db,
            participant.user_id,
        )

        if participant_user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"User with ID {participant.user_id} does not "
                    f"exist."
                ),
            )

        if participant.user_id == meeting.owner_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The meeting owner cannot be added as a participant",
            )

        existing = MeetingParticipantRepository.get_by_meeting_and_user(
            db,
            meeting_id,
            participant.user_id,
        )

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a participant",
            )

        db_participant = MeetingParticipant(
            meeting_id=meeting_id,
            user_id=participant.user_id,
        )

        return MeetingParticipantRepository.create(db, db_participant)

    @staticmethod
    def get_participants(
        db: Session,
        meeting_id: int,
        current_user: User,
    ):
        meeting = MeetingRepository.get_by_id(db, meeting_id)

        if meeting is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting not found",
            )

        is_owner = meeting.owner_id == current_user.id

        is_participant = MeetingParticipantRepository.get_by_meeting_and_user(
            db,
            meeting_id,
            current_user.id,
        ) is not None

        if not is_owner and not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "You must be the meeting owner or a participant "
                    "to view this list."
                ),
            )

        return MeetingParticipantRepository.get_by_meeting(
            db,
            meeting_id,
        )

    @staticmethod
    def update_status(
        db: Session,
        participant_id: int,
        participant_update: ParticipantUpdate,
        current_user: User,
    ):
        participant = MeetingParticipantRepository.get_by_id(
            db,
            participant_id,
        )

        if participant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found",
            )

        if participant.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can update only your own invitation",
            )

        participant.status = participant_update.status

        return MeetingParticipantRepository.update(
            db,
            participant,
        )

    @staticmethod
    def remove_participant(
        db: Session,
        participant_id: int,
        current_user: User,
    ):
        participant = MeetingParticipantRepository.get_by_id(
            db,
            participant_id,
        )

        if participant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Participant not found",
            )

        meeting = MeetingRepository.get_by_id(
            db,
            participant.meeting_id,
        )

        if meeting.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the meeting owner can remove participants",
            )

        MeetingParticipantRepository.delete(db, participant)

        return {
            "message": "Participant removed successfully"
        }
