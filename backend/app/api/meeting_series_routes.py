from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting import MeetingResponse
from app.schemas.meeting_series import (
    MeetingSeriesCreate,
    MeetingSeriesResponse,
    SeriesUpdateFromRequest,
)
from app.services.meeting_series_service import MeetingSeriesService

router = APIRouter(
    prefix="/meeting-series",
    tags=["Recurring Meetings"],
)


@router.post(
    "/",
    response_model=MeetingSeriesResponse,
    status_code=201,
)
def create_meeting_series(
    payload: MeetingSeriesCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingSeriesService.create_series(db, payload, current_user)


@router.get(
    "/{series_id}",
    response_model=MeetingSeriesResponse,
)
def get_meeting_series(
    series_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingSeriesService.get_series(db, series_id, current_user)


@router.put(
    "/{series_id}/from/{sequence}",
    response_model=list[MeetingResponse],
)
def update_meeting_series_from(
    series_id: int,
    sequence: int,
    payload: SeriesUpdateFromRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingSeriesService.update_series_from(
        db, series_id, sequence, payload, current_user,
    )


@router.delete("/{series_id}/from/{sequence}")
def cancel_meeting_series_from(
    series_id: int,
    sequence: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cancelled_count = MeetingSeriesService.cancel_series_from(
        db, series_id, sequence, current_user,
    )
    return {
        "message": f"Cancelled {cancelled_count} occurrence(s).",
        "cancelled_count": cancelled_count,
    }
