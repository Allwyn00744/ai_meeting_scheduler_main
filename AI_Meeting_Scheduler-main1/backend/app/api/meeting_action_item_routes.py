"""
Meeting Intelligence V3 — AI Action Item Extraction. Generates
Gemini-produced action items from the meeting's existing Meeting Note
V1 (app/api/meeting_note_routes.py) and exposes them for reading,
status updates, and deletion.

Distinct from app/api/ai_routes.py (POST /ai/meetings/{id}/summary,
freeform notes text + action items) and
app/api/meeting_intelligence_routes.py
(GET /meetings/{id}/action-items, PATCH /action-items/{id}).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_action_item import (
    ActionItemStatusUpdate,
    MeetingOwnerActionItemResponse,
)
from app.services.meeting_action_item_service import (
    MeetingActionItemService,
)

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Action Items"],
)


@router.post(
    "/action-items/{meeting_id}",
    response_model=list[MeetingOwnerActionItemResponse],
)
def generate_action_items(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingActionItemService.generate_action_items(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/action-items/{meeting_id}",
    response_model=list[MeetingOwnerActionItemResponse],
)
def list_action_items(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingActionItemService.list_action_items(
        db,
        meeting_id,
        current_user,
    )


@router.put(
    "/action-items/{action_item_id}",
    response_model=MeetingOwnerActionItemResponse,
)
def update_action_item_status(
    action_item_id: int,
    payload: ActionItemStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingActionItemService.update_status(
        db,
        action_item_id,
        payload,
        current_user,
    )


@router.delete(
    "/action-items/{action_item_id}",
)
def delete_action_item(
    action_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingActionItemService.delete_action_item(
        db,
        action_item_id,
        current_user,
    )
