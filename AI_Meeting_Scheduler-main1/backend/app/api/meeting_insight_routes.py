"""
Meeting Intelligence V5 — AI Meeting Insights. Generates/regenerates
Gemini-produced insights (key points, decisions, risks, next steps,
overall status) from the meeting's existing Meeting Note V1
(app/api/meeting_note_routes.py) and Meeting Summary V2
(app/api/meeting_summary_routes.py), and exposes them for reading.

Distinct from app/api/ai_routes.py and
app/api/meeting_intelligence_routes.py, which belong to the older AI
Meeting Intelligence pipeline.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting_insight import MeetingOwnerInsightResponse
from app.services.meeting_insight_service import MeetingInsightService

router = APIRouter(
    prefix="/meeting-intelligence",
    tags=["Meeting Insights"],
)


@router.post(
    "/insights/{meeting_id}",
    response_model=MeetingOwnerInsightResponse,
)
def generate_insight(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingInsightService.generate_insight(
        db,
        meeting_id,
        current_user,
    )


@router.get(
    "/insights/{meeting_id}",
    response_model=MeetingOwnerInsightResponse,
)
def get_insight(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingInsightService.get_insight(
        db,
        meeting_id,
        current_user,
    )
