from sqlalchemy.orm import Session

from app.models.meeting_action_item import MeetingActionItem


class MeetingActionItemRepository:
    """
    Write methods here never call db.commit() or db.rollback() — the
    caller (MeetingIntelligenceService) owns the transaction boundary
    across notes + summary + action item writes.
    """

    @staticmethod
    def get_by_meeting_id(db: Session, meeting_id: int):
        return (
            db.query(MeetingActionItem)
            .filter(MeetingActionItem.meeting_id == meeting_id)
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, action_item_id: int):
        return (
            db.query(MeetingActionItem)
            .filter(MeetingActionItem.id == action_item_id)
            .first()
        )

    @staticmethod
    def delete_by_meeting_id(db: Session, meeting_id: int) -> None:
        db.query(MeetingActionItem).filter(
            MeetingActionItem.meeting_id == meeting_id
        ).delete(synchronize_session=False)
        db.flush()

    @staticmethod
    def create_many(
        db: Session,
        items: list[MeetingActionItem],
    ) -> list[MeetingActionItem]:
        db.add_all(items)
        db.flush()
        return items

    @staticmethod
    def update_status(
        db: Session,
        item: MeetingActionItem,
        status: str,
    ) -> MeetingActionItem:
        item.status = status
        db.flush()
        return item
