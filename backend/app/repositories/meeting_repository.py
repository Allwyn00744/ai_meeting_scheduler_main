from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from datetime import date


from app.models.meeting import Meeting


class MeetingRepository:

    @staticmethod
    def create(db: Session, meeting: Meeting):
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        return meeting

    @staticmethod
    def get_all(
        db: Session,
        owner_id: int,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            db.query(Meeting)
            .filter(Meeting.owner_id == owner_id)
            .order_by(Meeting.start_time.desc())
        )

        if limit is not None:
            query = query.offset(offset).limit(limit)

        return query.all()

    @staticmethod
    def get_by_id(db: Session, meeting_id: int):
        return (
            db.query(Meeting)
            .filter(Meeting.id == meeting_id)
            .first()
        )

    @staticmethod
    def update(db: Session, meeting: Meeting):
        db.commit()
        db.refresh(meeting)
        return meeting

    @staticmethod
    def delete(db: Session, meeting: Meeting):
        db.delete(meeting)
        db.commit()

    @staticmethod
    def get_user_meetings(
        db: Session,
        owner_id: int,
    ):
        """
        Returns the complete, unpaginated set of meetings owned by a
        user. Used for conflict/availability checks, which must see
        every meeting to be correct — this method must never be
        paginated.
        """
        return (
            db.query(Meeting)
            .filter(Meeting.owner_id == owner_id)
            .all()
        )

    @staticmethod
    def search_meetings(
        db: Session,
        owner_id: int,
        keyword: str,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                or_(
                    Meeting.title.ilike(f"%{keyword}%"),
                    Meeting.description.ilike(f"%{keyword}%"),
                ),
            )
            .order_by(Meeting.start_time.desc())
        )

        if limit is not None:
            query = query.offset(offset).limit(limit)

        return query.all()

    @staticmethod
    def filter_by_status(
        db: Session,
        owner_id: int,
        status: str,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                Meeting.status == status,
            )
            .order_by(Meeting.start_time.desc())
        )

        if limit is not None:
            query = query.offset(offset).limit(limit)

        return query.all()

    @staticmethod
    def filter_by_date(
        db: Session,
        owner_id: int,
        meeting_date: date,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                func.date(Meeting.start_time) == meeting_date,
            )
            .order_by(Meeting.start_time.desc())
        )

        if limit is not None:
            query = query.offset(offset).limit(limit)

        return query.all()

    @staticmethod
    def filter_by_date_range(
        db: Session,
        owner_id: int,
        start_date: date,
        end_date: date,
        limit: int | None = None,
        offset: int = 0,
    ):
        query = (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                func.date(Meeting.start_time) >= start_date,
                func.date(Meeting.start_time) <= end_date,
            )
            .order_by(Meeting.start_time.desc())
        )

        if limit is not None:
            query = query.offset(offset).limit(limit)

        return query.all()

    @staticmethod
    def get_meetings_between(
        db: Session,
        owner_id: int,
        start_time,
        end_time,
    ):
        """
        Used for conflict detection during scheduling/suggestion —
        must never be paginated.
        """
        return (
            db.query(Meeting)
            .filter(
                Meeting.owner_id == owner_id,
                Meeting.start_time < end_time,
                Meeting.end_time > start_time,
            )
            .all()
        )

    @staticmethod
    def get_resource_bookings_between(
        db: Session,
        resource_id: int,
        start_time,
        end_time,
    ):
        """
        Used for resource conflict detection during scheduling — must
        never be paginated.
        """
        return (
            db.query(Meeting)
            .filter(
                Meeting.resource_id == resource_id,
                Meeting.start_time < end_time,
                Meeting.end_time > start_time,
            )
            .all()
        )
