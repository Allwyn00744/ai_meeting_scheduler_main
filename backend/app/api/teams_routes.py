from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.db.database import get_db
from app.services.meeting_service import MeetingService
from app.services.teams_meeting_service import TeamsMeetingService

router = APIRouter(
    prefix="/teams",
    tags=["Microsoft Teams Meetings"],
)


@router.get("/status")
def teams_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Reflects whether Microsoft Teams meetings are available for this
    user, which is exactly whether Outlook Calendar is connected -
    there is no separate Teams connection to check. Unlike
    /outlook/status and /zoom/status, there is deliberately no
    /teams/connect, /teams/callback, or /teams/disconnect: connecting
    or disconnecting Outlook already covers Teams.
    """
    return TeamsMeetingService.get_connection_status(
        db,
        current_user.id,
    )


@router.post("/sync/{meeting_id}")
def sync_meeting_to_teams(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.create_teams_sync(
        db,
        meeting_id,
        current_user,
    )


@router.put("/sync/{meeting_id}")
def update_teams_sync(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.update_teams_sync(
        db,
        meeting_id,
        current_user,
    )


@router.delete("/sync/{meeting_id}")
def delete_teams_sync(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.delete_teams_sync(
        db,
        meeting_id,
        current_user,
    )
