from sqlalchemy.orm import Session

from app.models.availability import Availability


class AvailabilityRepository:

    @staticmethod
    def create(db: Session, availability: Availability):
        db.add(availability)
        db.commit()
        db.refresh(availability)
        return availability

    @staticmethod
    def get_by_id(db: Session, availability_id: int):
        return (
            db.query(Availability)
            .filter(Availability.id == availability_id)
            .first()
        )

    @staticmethod
    def get_by_user(db: Session, user_id: int):
        return (
            db.query(Availability)
            .filter(Availability.user_id == user_id)
            .order_by(Availability.day_of_week)
            .all()
        )

    @staticmethod
    def update(db: Session, availability: Availability):
        db.commit()
        db.refresh(availability)
        return availability

    @staticmethod
    def delete(db: Session, availability: Availability):
        db.delete(availability)
        db.commit()
    @staticmethod
    def get_by_user_and_day(
        db: Session,
        user_id: int,
        day: str,
    ):
        return (
            db.query(Availability)
            .filter(
                Availability.user_id == user_id,
                Availability.day_of_week == day,
                Availability.is_available == True,
            )
            .first()
        )