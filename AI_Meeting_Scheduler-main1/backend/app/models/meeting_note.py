from datetime import datetime

from sqlalchemy import (
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MeetingNote(Base):
    """
    Manually authored meeting note (Meeting Notes V1). Distinct from
    MeetingNotes (app/models/meeting_notes.py, table meeting_notes),
    which stores AI transcript/summary-pipeline content and is owned
    by MeetingIntelligenceService. This table is owned/written only
    by MeetingNoteService, via the meeting owner.
    """

    __tablename__ = "meeting_owner_notes"

    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            name="uq_meeting_owner_notes_meeting_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
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
