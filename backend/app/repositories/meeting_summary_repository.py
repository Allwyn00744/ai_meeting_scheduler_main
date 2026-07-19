from sqlalchemy.orm import Session

from app.models.meeting_summary import MeetingSummary


class MeetingSummaryRepository:
    """
    Write methods here never call db.commit() or db.rollback() — the
    caller (MeetingIntelligenceService) owns the transaction boundary
    across notes + summary + action item writes.
    """

    @staticmethod
    def get_by_meeting_id(db: Session, meeting_id: int):
        return (
            db.query(MeetingSummary)
            .filter(MeetingSummary.meeting_id == meeting_id)
            .first()
        )

    @staticmethod
    def insert(
        db: Session,
        meeting_id: int,
        summary_text: str,
        source_notes_id: int | None,
        generated_by_id: int,
    ) -> MeetingSummary:
        summary = MeetingSummary(
            meeting_id=meeting_id,
            summary_text=summary_text,
            source_notes_id=source_notes_id,
            generated_by_id=generated_by_id,
        )
        db.add(summary)
        db.flush()
        return summary

    @staticmethod
    def update_summary(
        db: Session,
        summary: MeetingSummary,
        summary_text: str,
        source_notes_id: int | None,
        generated_by_id: int,
    ) -> MeetingSummary:
        summary.summary_text = summary_text
        summary.source_notes_id = source_notes_id
        # generated_by_id is updated on every successful regeneration —
        # it records who most recently generated the summary.
        summary.generated_by_id = generated_by_id
        db.flush()
        return summary
