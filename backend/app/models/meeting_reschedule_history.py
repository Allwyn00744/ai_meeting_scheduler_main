from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class MeetingRescheduleHistory(Base):
    """
    Reschedule Analytics V1: one row per reschedule (written by
    MeetingService.update_meeting whenever start_time/end_time
    actually change, which also covers SchedulerService's
    auto_reschedule_meeting since it persists through update_meeting).
    A meeting's start_time/end_time are overwritten in place, so this
    table is the only record of where it used to be.
    """

    __tablename__ = "meeting_reschedule_history"

    __table_args__ = (
        Index(
            "ix_meeting_reschedule_history_meeting_id",
            "meeting_id",
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

    previous_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    previous_end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    new_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    new_end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    rescheduled_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
