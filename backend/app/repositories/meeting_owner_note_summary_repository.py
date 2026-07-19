from sqlalchemy.orm import Session

from app.models.meeting_owner_note_summary import MeetingOwnerNoteSummary


class MeetingOwnerNoteSummaryRepository:
    """
    Write methods here never call db.commit() or db.rollback() - the
    caller (MeetingSummaryService) owns the transaction boundary.
    """

    @staticmethod
    def get_by_meeting_note_id(db: Session, meeting_note_id: int):
        return (
            db.query(MeetingOwnerNoteSummary)
            .filter(
                MeetingOwnerNoteSummary.meeting_note_id == meeting_note_id
            )
            .first()
        )

    @staticmethod
    def insert(
        db: Session,
        meeting_note_id: int,
        summary_text: str,
    ) -> MeetingOwnerNoteSummary:
        summary = MeetingOwnerNoteSummary(
            meeting_note_id=meeting_note_id,
            summary=summary_text,
        )
        db.add(summary)
        db.flush()
        return summary

    @staticmethod
    def update_summary(
        db: Session,
        summary: MeetingOwnerNoteSummary,
        summary_text: str,
    ) -> MeetingOwnerNoteSummary:
        summary.summary = summary_text
        db.flush()
        return summary
