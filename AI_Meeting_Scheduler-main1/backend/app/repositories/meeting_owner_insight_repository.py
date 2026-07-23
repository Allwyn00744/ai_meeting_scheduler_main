from sqlalchemy.orm import Session

from app.models.meeting_owner_insight import MeetingOwnerInsight


class MeetingOwnerInsightRepository:
    """
    Write methods here never call db.commit() or db.rollback() - the
    caller (MeetingInsightService) owns the transaction boundary.
    """

    @staticmethod
    def get_by_meeting_note_id(db: Session, meeting_note_id: int):
        return (
            db.query(MeetingOwnerInsight)
            .filter(
                MeetingOwnerInsight.meeting_note_id == meeting_note_id
            )
            .first()
        )

    @staticmethod
    def insert(
        db: Session,
        meeting_note_id: int,
        key_points: list[str],
        decisions: list[str],
        risks: list[str],
        next_steps: list[str],
        overall_status: str,
    ) -> MeetingOwnerInsight:
        insight = MeetingOwnerInsight(
            meeting_note_id=meeting_note_id,
            key_points_json=key_points,
            decisions_json=decisions,
            risks_json=risks,
            next_steps_json=next_steps,
            overall_status=overall_status,
        )
        db.add(insight)
        db.flush()
        return insight

    @staticmethod
    def update_insight(
        db: Session,
        insight: MeetingOwnerInsight,
        key_points: list[str],
        decisions: list[str],
        risks: list[str],
        next_steps: list[str],
        overall_status: str,
    ) -> MeetingOwnerInsight:
        insight.key_points_json = key_points
        insight.decisions_json = decisions
        insight.risks_json = risks
        insight.next_steps_json = next_steps
        insight.overall_status = overall_status
        db.flush()
        return insight
