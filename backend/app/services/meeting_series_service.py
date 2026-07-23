"""
MeetingSeriesService - Recurring Meetings V1: a true series (daily/
weekly/monthly cadence, "this and following" edit/cancel). Distinct
from and does not touch the existing weekly-only bulk-create in
scheduler_service.py (ScheduleMeetingRequest.repeat/repeat_type
/occurrences), which keeps working exactly as it did before.

Every occurrence is created via the existing, unmodified
MeetingService.create_meeting - this reuses conflict detection,
resource booking, Google/Outlook sync, and all 4 notification
channels for free, with no duplicated logic. "This and following"
edit/cancel likewise reuse MeetingService.update_meeting/delete_meeting
per occurrence rather than writing a second copy of what those already
do. A mid-series failure reuses SchedulerService's existing
_cleanup_created_occurrences compensation method instead of a new one.
"""
import calendar
import logging
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.meeting_series import MeetingSeries
from app.models.user import User
from app.repositories.meeting_series_repository import (
    MeetingSeriesRepository,
)
from app.schemas.meeting import MeetingCreate, MeetingUpdate
from app.schemas.meeting_series import (
    MeetingSeriesCreate,
    SeriesUpdateFromRequest,
)
from app.services.meeting_service import MeetingService

logger = logging.getLogger(__name__)


def _add_months(moment: datetime, months: int) -> datetime:
    """
    No new dependency (e.g. python-dateutil) needed for this - clamps
    to the last real day of the target month (e.g. Jan 31 + 1 month ->
    Feb 28/29, not an invalid Feb 31).
    """
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    day = min(moment.day, last_day_of_month)
    return moment.replace(year=year, month=month, day=day)


def _advance(moment: datetime, cadence: str, interval: int) -> datetime:
    if cadence == "daily":
        return moment + timedelta(days=interval)
    if cadence == "weekly":
        return moment + timedelta(weeks=interval)
    if cadence == "monthly":
        return _add_months(moment, interval)
    raise ValueError(f"Unknown cadence: {cadence}")


class MeetingSeriesService:

    @staticmethod
    def create_series(
        db: Session,
        payload: MeetingSeriesCreate,
        current_user: User,
    ) -> MeetingSeries:
        duration = payload.end_time - payload.start_time

        series = MeetingSeriesRepository.create(
            db,
            MeetingSeries(
                owner_id=current_user.id,
                title=payload.title,
                description=payload.description,
                location=payload.location,
                resource_id=payload.resource_id,
                cadence=payload.cadence,
                interval=payload.interval,
                occurrence_count=payload.occurrence_count,
            ),
        )

        created_meeting_ids: list[int] = []
        occurrence_start = payload.start_time

        try:
            for sequence in range(payload.occurrence_count):
                occurrence_end = occurrence_start + duration

                db_meeting = MeetingService.create_meeting(
                    db,
                    MeetingCreate(
                        title=payload.title,
                        description=payload.description,
                        start_time=occurrence_start,
                        end_time=occurrence_end,
                        location=payload.location,
                        resource_id=payload.resource_id,
                        external_guest_emails=payload.external_guest_emails,
                    ),
                    current_user,
                    series_id=series.id,
                    series_sequence=sequence,
                )
                created_meeting_ids.append(db_meeting.id)

                occurrence_start = _advance(
                    occurrence_start, payload.cadence, payload.interval,
                )
        except HTTPException:
            # Mirrors SchedulerService.schedule_meeting's own handling
            # of the identical failure mode (a conflict partway
            # through a multi-occurrence batch) - reuses the same
            # compensating cleanup rather than a second copy of it.
            from app.services.scheduler_service import SchedulerService

            SchedulerService._cleanup_created_occurrences(
                db, created_meeting_ids,
            )
            MeetingSeriesRepository.delete(db, series)
            raise

        db.refresh(series)
        return series

    @staticmethod
    def get_series(
        db: Session,
        series_id: int,
        current_user: User,
    ) -> MeetingSeries:
        series = MeetingSeriesRepository.get_by_id(db, series_id)

        if series is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meeting series not found.",
            )

        if series.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized.",
            )

        return series

    @staticmethod
    def update_series_from(
        db: Session,
        series_id: int,
        from_sequence: int,
        payload: SeriesUpdateFromRequest,
        current_user: User,
    ) -> list:
        """
        "Edit this and following": title/description/location
        /resource_id are applied as given; a time change is a fixed
        shift applied uniformly (see SeriesUpdateFromRequest's
        docstring) so each occurrence keeps its own original date.
        """
        series = MeetingSeriesService.get_series(db, series_id, current_user)

        occurrences = MeetingSeriesRepository.get_occurrences(
            db, series.id, from_sequence=from_sequence,
        )

        if not occurrences:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No occurrences found from that point in the series.",
            )

        update_fields = payload.model_dump(
            exclude_unset=True, exclude={"time_shift_minutes"},
        )

        updated = []
        for meeting in occurrences:
            fields = dict(update_fields)

            if payload.time_shift_minutes:
                shift = timedelta(minutes=payload.time_shift_minutes)
                fields["start_time"] = meeting.start_time + shift
                fields["end_time"] = meeting.end_time + shift

            if fields:
                updated_meeting = MeetingService.update_meeting(
                    db, meeting.id, MeetingUpdate(**fields), current_user,
                )
                updated.append(updated_meeting)
            else:
                updated.append(meeting)

        return updated

    @staticmethod
    def cancel_series_from(
        db: Session,
        series_id: int,
        from_sequence: int,
        current_user: User,
    ) -> int:
        """
        "Cancel this and following" - reuses the existing, unmodified
        MeetingService.delete_meeting per occurrence (the same
        soft-delete-with-audit-trail every other cancellation in this
        app already goes through). Cancelling a single occurrence
        needs no series-aware code at all: DELETE /meetings/{id}
        already works standalone regardless of series_id.
        """
        series = MeetingSeriesService.get_series(db, series_id, current_user)

        occurrences = MeetingSeriesRepository.get_occurrences(
            db, series.id, from_sequence=from_sequence,
        )

        for meeting in occurrences:
            MeetingService.delete_meeting(db, meeting.id, current_user)

        return len(occurrences)
