from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.models.meeting_series import MeetingSeries


class MeetingSeriesRepository:

    @staticmethod
    def create(db: Session, series: MeetingSeries) -> MeetingSeries:
        db.add(series)
        db.commit()
        db.refresh(series)
        return series

    @staticmethod
    def get_by_id(db: Session, series_id: int) -> MeetingSeries | None:
        return (
            db.query(MeetingSeries)
            .filter(MeetingSeries.id == series_id)
            .first()
        )

    @staticmethod
    def delete(db: Session, series: MeetingSeries) -> None:
        db.delete(series)
        db.commit()

    @staticmethod
    def get_occurrences(
        db: Session,
        series_id: int,
        from_sequence: int | None = None,
    ) -> list[Meeting]:
        """
        Non-cancelled occurrences of a series, optionally restricted
        to sequence >= from_sequence ("this and following"). Excludes
        cancelled rows for the same reason every other meeting listing
        in this app does (see MeetingRepository) - a cancelled
        occurrence has already been individually soft-deleted via the
        normal DELETE /meetings/{id} and shouldn't be editable or
        re-cancelled as part of a bulk series operation.
        """
        query = db.query(Meeting).filter(
            Meeting.series_id == series_id,
            Meeting.status != "cancelled",
        )

        if from_sequence is not None:
            query = query.filter(Meeting.series_sequence >= from_sequence)

        return query.order_by(Meeting.series_sequence).all()
