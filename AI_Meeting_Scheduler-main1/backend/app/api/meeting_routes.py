from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.db.database import get_db
from app.models.user import User
from app.schemas.meeting import (
    MeetingCreate,
    MeetingUpdate,
    MeetingResponse,
)
from app.services.meeting_service import MeetingService

router = APIRouter(
    prefix="/meetings",
    tags=["Meetings"],
)


@router.post(
    "/",
    response_model=MeetingResponse,
    status_code=201,
)
def create_meeting(
    meeting: MeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.create_meeting(
        db,
        meeting,
        current_user,
    )


@router.get(
    "/",
    response_model=list[MeetingResponse],
)
def get_my_meetings(
    limit: int | None = Query(
        default=None, ge=1, le=settings.MAX_PAGE_SIZE
    ),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.get_my_meetings(
        db,
        current_user,
        limit=limit,
        offset=offset,
    )


@router.get("/search")
def search_meetings(
    keyword: str = Query(...),
    limit: int | None = Query(
        default=None, ge=1, le=settings.MAX_PAGE_SIZE
    ),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.search_meetings(
        db,
        keyword,
        current_user,
        limit=limit,
        offset=offset,
    )


@router.get("/filter/status")
def filter_by_status(
    status: str = Query(...),
    limit: int | None = Query(
        default=None, ge=1, le=settings.MAX_PAGE_SIZE
    ),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.filter_by_status(
        db,
        status,
        current_user,
        limit=limit,
        offset=offset,
    )


@router.put(
    "/{meeting_id}",
    response_model=MeetingResponse,
)
def update_meeting(
    meeting_id: int,
    meeting: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.update_meeting(
        db,
        meeting_id,
        meeting,
        current_user,
    )


@router.delete(
    "/{meeting_id}",
)
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.delete_meeting(
        db,
        meeting_id,
        current_user,
    )


@router.get("/filter/date")
def filter_by_date(
    meeting_date: date = Query(...),
    limit: int | None = Query(
        default=None, ge=1, le=settings.MAX_PAGE_SIZE
    ),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.filter_by_date(
        db,
        meeting_date,
        current_user,
        limit=limit,
        offset=offset,
    )


@router.get("/filter/range")
def filter_by_date_range(
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int | None = Query(
        default=None, ge=1, le=settings.MAX_PAGE_SIZE
    ),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.filter_by_date_range(
        db,
        start_date,
        end_date,
        current_user,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{meeting_id}",
    response_model=MeetingResponse,
)
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.get_meeting_by_id(
        db,
        meeting_id,
        current_user,
    )
