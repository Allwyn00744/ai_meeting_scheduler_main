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


class MeetingOwnerFollowUpEmail(Base):
    """
    AI-generated follow-up email drafted from a Meeting Note V1
    (app/models/meeting_note.py, table meeting_owner_notes) and its
    Meeting Summary V2 (app/models/meeting_owner_note_summary.py).
    Owned exclusively by Meeting Intelligence V4
    (MeetingFollowUpEmailService).

    Deliberately separate from the older AI Meeting Intelligence
    pipeline's follow-up draft (AIMeetingService.generate_follow_up,
    POST /ai/meetings/{id}/follow-up), which sources freeform notes
    text and is never persisted. This table must never be read or
    written by that pipeline, and vice versa.
    """

    __tablename__ = "meeting_owner_followup_emails"

    __table_args__ = (
        UniqueConstraint(
            "meeting_note_id",
            name="uq_meeting_owner_followup_emails_meeting_note_id",
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

    subject: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    body: Mapped[str] = mapped_column(
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
