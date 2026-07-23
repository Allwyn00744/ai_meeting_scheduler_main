from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.scheduler import (
    AutoRescheduleResponse,
    ScheduleMeetingRequest,
    ScheduleMeetingResponse,
    SuggestSlotsResponse,
)

from app.services.scheduler_service import SchedulerService

router = APIRouter(
    prefix="/scheduler",
    tags=["Scheduler"],
)


@router.post(
    "/schedule",
    response_model=ScheduleMeetingResponse,
    status_code=201,
)
def schedule_meeting(
    meeting: ScheduleMeetingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SchedulerService.schedule_meeting(
        db,
        meeting,
        current_user,
    )
@router.post(
    "/suggest-slots",
    response_model=SuggestSlotsResponse,
)
def suggest_slots(
    meeting: ScheduleMeetingRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SchedulerService.suggest_slots(
        db,
        meeting,
        current_user,
    )


@router.get(
    "/meetings/{meeting_id}/reschedule-suggestions",
    response_model=SuggestSlotsResponse,
)
def suggest_reschedule_slots(
    meeting_id: int,
    window_days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SchedulerService.suggest_reschedule_slots(
        db,
        meeting_id,
        current_user,
        window_days=window_days,
    )


@router.post(
    "/meetings/{meeting_id}/auto-reschedule",
    response_model=AutoRescheduleResponse,
)
def auto_reschedule_meeting(
    meeting_id: int,
    window_days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SchedulerService.auto_reschedule_meeting(
        db,
        meeting_id,
        current_user,
        window_days=window_days,
    )