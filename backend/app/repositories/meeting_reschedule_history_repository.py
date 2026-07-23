from datetime import datetime

from sqlalchemy.orm import Session

from app.models.meeting_reschedule_history import MeetingRescheduleHistory


class MeetingRescheduleHistoryRepository:

    @staticmethod
    def create(
        db: Session,
        meeting_id: int,
        previous_start_time: datetime,
        previous_end_time: datetime,
        new_start_time: datetime,
        new_end_time: datetime,
        rescheduled_by_id: int,
    ) -> MeetingRescheduleHistory:
        row = MeetingRescheduleHistory(
            meeting_id=meeting_id,
            previous_start_time=previous_start_time,
            previous_end_time=previous_end_time,
            new_start_time=new_start_time,
            new_end_time=new_end_time,
            rescheduled_by_id=rescheduled_by_id,
        )

        db.add(row)
        db.flush()

        return row

    @staticmethod
    def get_between(
        db: Session,
        owner_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> list[MeetingRescheduleHistory]:
        """
        All reschedule events in [start_time, end_time) for meetings
        currently owned by owner_id - joins to Meeting rather than
        filtering on rescheduled_by_id, since the meeting owner (not
        necessarily whoever triggered a given reschedule) is the
        analytics scoping boundary used everywhere else.
        """
        from app.models.meeting import Meeting

        return (
            db.query(MeetingRescheduleHistory)
            .join(Meeting, Meeting.id == MeetingRescheduleHistory.meeting_id)
            .filter(
                Meeting.owner_id == owner_id,
                MeetingRescheduleHistory.created_at >= start_time,
                MeetingRescheduleHistory.created_at < end_time,
            )
            .all()
        )
