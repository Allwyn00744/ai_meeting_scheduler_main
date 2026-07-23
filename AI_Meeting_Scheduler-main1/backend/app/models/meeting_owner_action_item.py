from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MeetingOwnerActionItem(Base):
    """
    AI-extracted action item sourced from a Meeting Note V1
    (app/models/meeting_note.py, table meeting_owner_notes). Owned
    exclusively by Meeting Intelligence V3
    (MeetingActionItemService).

    Deliberately separate from MeetingActionItem
    (app/models/meeting_action_item.py, table meeting_action_items),
    which is owned by the older AI Meeting Intelligence pipeline
    (AIMeetingService / MeetingIntelligenceService) and is keyed off
    meeting_summaries.id, not meeting_owner_notes. This table must
    never be read or written by that pipeline, and vice versa.
    """

    __tablename__ = "meeting_owner_action_items"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    meeting_note_id: Mapped[int] = mapped_column(
        ForeignKey("meeting_owner_notes.id", ondelete="CASCADE"),
        nullable=False,
    )

    task: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    assignee: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    priority: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="Pending",
        server_default="Pending",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
