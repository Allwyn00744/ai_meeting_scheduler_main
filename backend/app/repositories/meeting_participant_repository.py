from sqlalchemy.orm import Session

from app.models.meeting_participant import MeetingParticipant


class MeetingParticipantRepository:

    @staticmethod
    def create(db: Session, participant: MeetingParticipant):
        db.add(participant)
        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def get_by_id(db: Session, participant_id: int):
        return (
            db.query(MeetingParticipant)
            .filter(MeetingParticipant.id == participant_id)
            .first()
        )

    @staticmethod
    def get_by_meeting(db: Session, meeting_id: int):
        return (
            db.query(MeetingParticipant)
            .filter(MeetingParticipant.meeting_id == meeting_id)
            .all()
        )

    @staticmethod
    def get_by_meeting_and_user(
        db: Session,
        meeting_id: int,
        user_id: int,
    ):
        return (
            db.query(MeetingParticipant)
            .filter(
                MeetingParticipant.meeting_id == meeting_id,
                MeetingParticipant.user_id == user_id,
            )
            .first()
        )

    @staticmethod
    def update(db: Session, participant: MeetingParticipant):
        db.commit()
        db.refresh(participant)
        return participant

    @staticmethod
    def delete(db: Session, participant: MeetingParticipant):
        db.delete(participant)
        db.commit()

    @staticmethod
    def create_many(
        db: Session,
        participants: list[MeetingParticipant],
    ):
        db.add_all(participants)
        db.commit()

        for participant in participants:
            db.refresh(participant)

        return participants