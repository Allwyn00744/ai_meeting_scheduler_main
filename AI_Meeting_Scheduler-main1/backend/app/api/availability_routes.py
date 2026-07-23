from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.availability import (
    AvailabilityCreate,
    AvailabilityUpdate,
    AvailabilityResponse,
)
from app.services.availability_service import AvailabilityService

router = APIRouter(
    prefix="/availability",
    tags=["Availability"],
)


@router.post(
    "/",
    response_model=AvailabilityResponse,
    status_code=201,
)
def create_availability(
    availability: AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AvailabilityService.create_availability(
        db,
        availability,
        current_user,
    )


@router.get(
    "/",
    response_model=list[AvailabilityResponse],
)
def get_my_availability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AvailabilityService.get_my_availability(
        db,
        current_user,
    )


@router.put(
    "/{availability_id}",
    response_model=AvailabilityResponse,
)
def update_availability(
    availability_id: int,
    availability: AvailabilityUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AvailabilityService.update_availability(
        db,
        availability_id,
        availability,
        current_user,
    )


@router.delete(
    "/{availability_id}",
)
def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return AvailabilityService.delete_availability(
        db,
        availability_id,
        current_user,
    )