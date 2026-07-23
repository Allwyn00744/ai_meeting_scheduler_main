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


class MeetingSummary(Base):
    __tablename__ = "meeting_summaries"

    __table_args__ = (
        UniqueConstraint(
            "meeting_id",
            name="uq_meeting_summaries_meeting_id",
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

    summary_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    source_notes_id: Mapped[int | None] = mapped_column(
        ForeignKey("meeting_notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    generated_by_id: Mapped[int] = mapped_column(
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
