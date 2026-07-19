"""
Read/update endpoints for persisted meeting intelligence records
(notes, summaries, action items). Generation itself happens via
POST /ai/meetings/{meeting_id}/summary in ai_routes.py — this router
only exposes access to what has already been persisted.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.ai import MeetingSummaryResponse
from app.schemas.meeting_intelligence import (
    ActionItemResponse,
    ActionItemStatusUpdate,
    MeetingNotesResponse,
)
from app.services.meeting_intelligence_service import (
    MeetingIntelligenceService,
)

router = APIRouter(
    tags=["Meeting Intelligence"],
)


@router.get(
    "/meetings/{meeting_id}/notes",
    response_model=MeetingNotesResponse,
)
def get_meeting_notes(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingIntelligenceService.get_notes(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/meetings/{meeting_id}/summary",
    response_model=MeetingSummaryResponse,
)
def get_meeting_summary(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingIntelligenceService.get_summary(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/meetings/{meeting_id}/action-items",
    response_model=list[ActionItemResponse],
)
def get_meeting_action_items(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingIntelligenceService.get_action_items(
        db,
        meeting_id,
        current_user,
    )


@router.patch(
    "/action-items/{action_item_id}",
    response_model=ActionItemResponse,
)
def update_action_item_status(
    action_item_id: int,
    body: ActionItemStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingIntelligenceService.update_action_item_status(
        db,
        action_item_id,
        body.status,
        current_user,
    )
