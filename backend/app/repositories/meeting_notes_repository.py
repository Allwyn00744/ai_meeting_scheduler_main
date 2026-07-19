from sqlalchemy.orm import Session

from app.models.meeting_notes import MeetingNotes


class MeetingNotesRepository:
    """
    Write methods here never call db.commit() or db.rollback() — the
    caller (MeetingIntelligenceService) owns the transaction boundary
    across notes + summary + action item writes.
    """

    @staticmethod
    def get_by_meeting_id(db: Session, meeting_id: int):
        return (
            db.query(MeetingNotes)
            .filter(MeetingNotes.meeting_id == meeting_id)
            .first()
        )

    @staticmethod
    def insert(
        db: Session,
        meeting_id: int,
        content: str,
        created_by_id: int,
    ) -> MeetingNotes:
        notes = MeetingNotes(
            meeting_id=meeting_id,
            content=content,
            created_by_id=created_by_id,
        )
        db.add(notes)
        db.flush()
        return notes

    @staticmethod
    def update_content(
        db: Session,
        notes: MeetingNotes,
        content: str,
    ) -> MeetingNotes:
        # created_by_id is intentionally never modified here — it
        # records who first created the notes row, not who last
        # regenerated it.
        notes.content = content
        db.flush()
        return notes
