"""
Meeting Intelligence V2 — AI Meeting Summary. Generates/regenerates a
Gemini-produced summary from the meeting's existing Meeting Note V1
(app/api/meeting_note_routes.py) and exposes it for reading.

Distinct from app/api/ai_routes.py (POST /ai/meetings/{id}/summary,
freeform notes text) and app/api/meeting_intelligence_routes.py
(GET /meetings/{id}/summary, notes+summary+action items pipeline).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_summary import MeetingAISummaryResponse
from app.services.meeting_summary_service import MeetingSummaryService

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Summary"],
)


@router.post(
    "/summary/{meeting_id}",
    response_model=MeetingAISummaryResponse,
)
def generate_summary(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingSummaryService.generate_summary(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/summary/{meeting_id}",
    response_model=MeetingAISummaryResponse,
)
def get_summary(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingSummaryService.get_summary(
        db,
        meeting_id,
        current_user,
    )
