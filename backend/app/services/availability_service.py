from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.cache import (
    AVAILABILITY_TTL_SECONDS,
    availability_list_key,
    cache_delete,
    cache_get,
    cache_set,
)
from app.models.availability import Availability
from app.models.user import User
from app.repositories.availability_repository import (
    AvailabilityRepository,
)
from app.repositories.user_repository import UserRepository


from app.schemas.availability import (
    AvailabilityCreate,
    AvailabilityResponse,
    AvailabilityUpdate,
)


class AvailabilityService:

    @staticmethod
    def create_availability(
        db: Session,
        availability: AvailabilityCreate,
        current_user: User,
    ):
        if availability.start_time >= availability.end_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start time must be before end time",
            )

        db_availability = Availability(
            user_id=current_user.id,
            day_of_week=availability.day_of_week,
            start_time=availability.start_time,
            end_time=availability.end_time,
            is_available=availability.is_available,
        )

        db_availability = AvailabilityRepository.create(
            db,
            db_availability,
        )

        cache_delete(availability_list_key(current_user.id))

        return db_availability

    @staticmethod
    def get_my_availability(
        db: Session,
        current_user: User,
    ):
        cache_key = availability_list_key(current_user.id)
        cached = cache_get(cache_key)

        if cached is not None:
            return cached

        availabilities = AvailabilityRepository.get_by_user(
            db,
            current_user.id,
        )

        serialized = [
            AvailabilityResponse.model_validate(
                availability
            ).model_dump(mode="json")
            for availability in availabilities
        ]

        if serialized:
            cache_set(cache_key, serialized, AVAILABILITY_TTL_SECONDS)

        return serialized

    @staticmethod
    def update_availability(
        db: Session,
        availability_id: int,
        availability_data: AvailabilityUpdate,
        current_user: User,
    ):
        availability = AvailabilityRepository.get_by_id(
            db,
            availability_id,
        )

        if availability is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Availability not found",
            )

        if availability.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        update_data = availability_data.model_dump(
            exclude_unset=True
        )

        # Resolve the effective start/end (existing value unless
        # this update replaces it) so a partial update can't leave
        # start >= end without being caught.
        effective_start = update_data.get(
            "start_time", availability.start_time
        )
        effective_end = update_data.get(
            "end_time", availability.end_time
        )

        if effective_start >= effective_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start time must be before end time",
            )

        for key, value in update_data.items():
            setattr(availability, key, value)

        availability = AvailabilityRepository.update(
            db,
            availability,
        )

        cache_delete(availability_list_key(current_user.id))

        return availability

    @staticmethod
    def delete_availability(
        db: Session,
        availability_id: int,
        current_user: User,
    ):
        availability = AvailabilityRepository.get_by_id(
            db,
            availability_id,
        )

        if availability is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Availability not found",
            )

        if availability.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized",
            )

        AvailabilityRepository.delete(
            db,
            availability,
        )

        cache_delete(availability_list_key(current_user.id))

        return {
            "message": "Availability deleted successfully"
        }

    @staticmethod
    def is_user_available(
        db: Session,
        user_id: int,
        meeting_start: datetime,
        meeting_end: datetime,
    ):
        # Meeting datetimes must be timezone-aware.
        if (
            meeting_start.tzinfo is None
            or meeting_start.utcoffset() is None
            or meeting_end.tzinfo is None
            or meeting_end.utcoffset() is None
        ):
            return False

        # Get the user so we can evaluate availability
        # in that user's local timezone.
        user = UserRepository.get_user_by_id(
            db,
            user_id,
        )

        if user is None:
            return False

        try:
            user_timezone = ZoneInfo(user.timezone)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            return False

        # Convert the absolute meeting times into the
        # user's local timezone before checking working hours.
        local_start = meeting_start.astimezone(user_timezone)
        local_end = meeting_end.astimezone(user_timezone)

        # Availability currently supports only meetings
        # contained within one local calendar day.
        if local_start.date() != local_end.date():
            return False

        day = local_start.strftime("%A")

        availability = (
            AvailabilityRepository.get_by_user_and_day(
                db,
                user_id,
                day,
            )
        )

        if availability is None:
            return False

        # Strip timezone information from the local datetime's
        # time component because availability.start_time and
        # availability.end_time are PostgreSQL TIME values.
        local_start_time = local_start.time().replace(tzinfo=None)
        local_end_time = local_end.time().replace(tzinfo=None)

        return (
            availability.is_available
            and availability.start_time <= local_start_time
            and availability.end_time >= local_end_time
        )