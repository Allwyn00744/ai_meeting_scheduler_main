"""
Meeting Notes V1 — manually authored, owner-written notes on a
meeting. Separate from app/api/meeting_intelligence_routes.py, which
exposes AI transcript/summary-pipeline content under /meetings/{id}.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_note import (
    MeetingNoteCreate,
    MeetingNoteResponse,
    MeetingNoteUpdate,
)
from app.services.meeting_note_service import MeetingNoteService

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Notes"],
)


@router.post(
    "/notes/{meeting_id}",
    response_model=MeetingNoteResponse,
    status_code=201,
)
def create_note(
    meeting_id: int,
    payload: MeetingNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingNoteService.create_note(
        db,
        meeting_id,
        payload,
        current_user,
    )


@router.get(
    "/notes/{meeting_id}",
    response_model=MeetingNoteResponse,
)
def get_note(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingNoteService.get_note(
        db,
        meeting_id,
        current_user,
    )


@router.put(
    "/notes/{meeting_id}",
    response_model=MeetingNoteResponse,
)
def update_note(
    meeting_id: int,
    payload: MeetingNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingNoteService.update_note(
        db,
        meeting_id,
        payload,
        current_user,
    )


@router.delete(
    "/notes/{meeting_id}",
)
def delete_note(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingNoteService.delete_note(
        db,
        meeting_id,
        current_user,
    )
