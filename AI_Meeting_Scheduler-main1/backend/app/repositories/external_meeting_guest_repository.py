from sqlalchemy.orm import Session

from app.models.external_meeting_guest import ExternalMeetingGuest


class ExternalMeetingGuestRepository:

    @staticmethod
    def create_many(
        db: Session,
        guests: list[ExternalMeetingGuest],
    ):
        db.add_all(guests)
        db.commit()

        for guest in guests:
            db.refresh(guest)

        return guests

    @staticmethod
    def get_by_meeting(db: Session, meeting_id: int):
        return (
            db.query(ExternalMeetingGuest)
            .filter(ExternalMeetingGuest.meeting_id == meeting_id)
            .all()
        )
