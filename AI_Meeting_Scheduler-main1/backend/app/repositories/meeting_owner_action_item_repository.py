from sqlalchemy.orm import Session

from app.models.meeting_owner_action_item import MeetingOwnerActionItem


class MeetingOwnerActionItemRepository:
    """
    Write methods here never call db.commit() or db.rollback() - the
    caller (MeetingActionItemService) owns the transaction boundary.
    """

    @staticmethod
    def get_by_meeting_note_id(db: Session, meeting_note_id: int):
        return (
            db.query(MeetingOwnerActionItem)
            .filter(
                MeetingOwnerActionItem.meeting_note_id == meeting_note_id
            )
            .order_by(MeetingOwnerActionItem.id.asc())
            .all()
        )

    @staticmethod
    def get_by_id(db: Session, action_item_id: int):
        return (
            db.query(MeetingOwnerActionItem)
            .filter(MeetingOwnerActionItem.id == action_item_id)
            .first()
        )

    @staticmethod
    def delete_by_meeting_note_id(
        db: Session,
        meeting_note_id: int,
    ) -> None:
        db.query(MeetingOwnerActionItem).filter(
            MeetingOwnerActionItem.meeting_note_id == meeting_note_id
        ).delete(synchronize_session=False)
        db.flush()

    @staticmethod
    def create_many(
        db: Session,
        items: list[MeetingOwnerActionItem],
    ) -> list[MeetingOwnerActionItem]:
        db.add_all(items)
        db.flush()
        return items

    @staticmethod
    def update_status(
        db: Session,
        item: MeetingOwnerActionItem,
        status: str,
    ) -> MeetingOwnerActionItem:
        item.status = status
        db.flush()
        return item

    @staticmethod
    def delete(db: Session, item: MeetingOwnerActionItem) -> None:
        db.delete(item)
        db.flush()
