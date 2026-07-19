from sqlalchemy.orm import Session

from app.models.meeting_note import MeetingNote


class MeetingNoteRepository:

    @staticmethod
    def create(db: Session, note: MeetingNote) -> MeetingNote:
        db.add(note)
        db.commit()
        db.refresh(note)
        return note

    @staticmethod
    def get_by_meeting_id(
        db: Session,
        meeting_id: int,
    ) -> MeetingNote | None:
        return (
            db.query(MeetingNote)
            .filter(MeetingNote.meeting_id == meeting_id)
            .first()
        )

    @staticmethod
    def get_by_id(
        db: Session,
        note_id: int,
    ) -> MeetingNote | None:
        return (
            db.query(MeetingNote)
            .filter(MeetingNote.id == note_id)
            .first()
        )

    @staticmethod
    def update(db: Session, note: MeetingNote) -> MeetingNote:
        db.commit()
        db.refresh(note)
        return note

    @staticmethod
    def delete(db: Session, note: MeetingNote) -> None:
        db.delete(note)
        db.commit()
