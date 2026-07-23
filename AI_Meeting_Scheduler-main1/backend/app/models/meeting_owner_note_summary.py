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


class MeetingOwnerNoteSummary(Base):
    """
    AI-generated summary of a Meeting Note V1 (app/models/meeting_note.py,
    table meeting_owner_notes). Owned exclusively by Meeting Intelligence
    V2 (MeetingSummaryService).

    Deliberately separate from MeetingSummary (app/models/meeting_summary.py,
    table meeting_summaries), which is owned by the older AI Meeting
    Intelligence pipeline (AIMeetingService / MeetingIntelligenceService)
    and summarizes freeform notes text (app/models/meeting_notes.py), not
    meeting_owner_notes. This table must never be read or written by
    that pipeline, and vice versa.
    """

    __tablename__ = "meeting_owner_note_summaries"

    __table_args__ = (
        UniqueConstraint(
            "meeting_note_id",
            name="uq_meeting_owner_note_summaries_meeting_note_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    meeting_note_id: Mapped[int] = mapped_column(
        ForeignKey("meeting_owner_notes.id", ondelete="CASCADE"),
        nullable=False,
    )

    summary: Mapped[str] = mapped_column(
        Text,
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
