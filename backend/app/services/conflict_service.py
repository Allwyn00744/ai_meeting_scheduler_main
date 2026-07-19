from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.repositories.meeting_repository import MeetingRepository


class ConflictService:

    @staticmethod
    def has_time_conflict(
        start_time,
        end_time,
        meetings: list[Meeting],
    ):
        """
        Check if a given time range overlaps with any meeting.
        """
        for meeting in meetings:
            if (
                start_time < meeting.end_time
                and end_time > meeting.start_time
            ):
                return True, meeting

        return False, None

    @staticmethod
    def check_user_conflict(
        db: Session,
        user_id: int,
        start_time,
        end_time,
    ):
        """
        Check whether a specific user has a conflicting meeting.
        """
        meetings = MeetingRepository.get_user_meetings(
            db,
            user_id,
        )

        return ConflictService.has_time_conflict(
            start_time,
            end_time,
            meetings,
        )
    
    @staticmethod
    def check_resource_conflict(
        db: Session,
        resource_id: int,
        start_time,
        end_time,
    ):
        """
        Check whether a resource has a conflicting booking. Overlap is
        determined at the SQL layer by MeetingRepository, so any row
        returned is already a genuine conflict (back-to-back bookings
        are excluded).
        """
        bookings = MeetingRepository.get_resource_bookings_between(
            db,
            resource_id,
            start_time,
            end_time,
        )

        if bookings:
            return True, bookings[0]

        return False, None

    @staticmethod
    def check_all_participants(
        db: Session,
        participant_ids: list[int],
        start_time,
        end_time,
    ):
        """
        Check whether any participant has a scheduling conflict.
        """

        for user_id in participant_ids:

            conflict, meeting = (
                ConflictService.check_user_conflict(
                    db,
                    user_id,
                    start_time,
                    end_time,
                )
            )

            if conflict:
                return True, user_id, meeting

        return False, None, None