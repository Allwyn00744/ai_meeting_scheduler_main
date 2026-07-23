from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MeetingOwnerInsight(Base):
    """
    AI-generated insights derived from a Meeting Note V1
    (app/models/meeting_note.py, table meeting_owner_notes) and its
    Meeting Summary V2 (app/models/meeting_owner_note_summary.py).
    Owned exclusively by Meeting Intelligence V5
    (MeetingInsightService).

    Deliberately separate from the older AI Meeting Intelligence
    pipeline (AIMeetingService / MeetingIntelligenceService,
    meeting_summaries / meeting_action_items), which this feature
    never reads, writes, calls, or otherwise depends on.
    """

    __tablename__ = "meeting_owner_insights"

    __table_args__ = (
        UniqueConstraint(
            "meeting_note_id",
            name="uq_meeting_owner_insights_meeting_note_id",
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

    key_points_json: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    decisions_json: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    risks_json: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    next_steps_json: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
    )

    overall_status: Mapped[str] = mapped_column(
        String(20),
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
