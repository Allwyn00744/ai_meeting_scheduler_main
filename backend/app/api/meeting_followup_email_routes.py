"""
Meeting Intelligence V4 — AI Follow-up Email Generation.
Generates/regenerates a Gemini-produced professional follow-up email
from the meeting's existing Meeting Note V1
(app/api/meeting_note_routes.py) and Meeting Summary V2
(app/api/meeting_summary_routes.py), optionally including AI Action
Items V3 (app/api/meeting_action_item_routes.py) when present, and
exposes it for reading. Generation only - this feature never sends
the email.

Distinct from app/api/ai_routes.py (POST /ai/meetings/{id}/follow-up,
freeform notes text, draft-only, never persisted).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_followup_email import MeetingFollowUpEmailResponse
from app.services.meeting_followup_email_service import (
    MeetingFollowUpEmailService,
)

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Follow-up Email"],
)


@router.post(
    "/follow-up/{meeting_id}",
    response_model=MeetingFollowUpEmailResponse,
)
def generate_followup_email(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingFollowUpEmailService.generate_followup_email(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/follow-up/{meeting_id}",
    response_model=MeetingFollowUpEmailResponse,
)
def get_followup_email(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingFollowUpEmailService.get_followup_email(
        db,
        meeting_id,
        current_user,
    )
