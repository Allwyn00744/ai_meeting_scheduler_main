from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_participant import (
    ParticipantCreate,
    ParticipantUpdate,
    ParticipantResponse,
)
from app.services.meeting_participant_service import (
    MeetingParticipantService,
)

router = APIRouter(
    tags=["Meeting Participants"],
)


@router.post(
    "/meetings/{meeting_id}/participants",
    response_model=ParticipantResponse,
    status_code=201,
)
def add_participant(
    meeting_id: int,
    participant: ParticipantCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingParticipantService.add_participant(
        db,
        meeting_id,
        participant,
        current_user,
    )


@router.get(
    "/meetings/{meeting_id}/participants",
    response_model=list[ParticipantResponse],
)
def get_participants(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingParticipantService.get_participants(
        db,
        meeting_id,
        current_user,
    )


@router.put(
    "/participants/{participant_id}",
    response_model=ParticipantResponse,
)
def update_participant_status(
    participant_id: int,
    participant: ParticipantUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingParticipantService.update_status(
        db,
        participant_id,
        participant,
        current_user,
    )


@router.delete(
    "/participants/{participant_id}",
)
def remove_participant(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingParticipantService.remove_participant(
        db,
        participant_id,
        current_user,
    )