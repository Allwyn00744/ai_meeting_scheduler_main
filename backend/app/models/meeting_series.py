from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class MeetingSeries(Base):
    """
    Recurring Meetings V1: the parent record for a true recurring
    series (daily/weekly/monthly cadence, "this and following"
    edit/cancel - see MeetingSeriesService). Deliberately separate
    from the existing weekly-only bulk-create in scheduler_service.py
    (ScheduleMeetingRequest.repeat/repeat_type/occurrences), which has
    no series concept at all and is untouched by this feature - each
    Meeting row it creates is fully independent, with no series_id.

    This table only stores the series' own parameters; the actual
    occurrences are ordinary rows in `meetings` (series_id +
    series_sequence), created via the existing
    MeetingService.create_meeting - see MeetingSeriesService.
    """

    __tablename__ = "meeting_series"

    __table_args__ = (
        CheckConstraint(
            "cadence IN ('daily', 'weekly', 'monthly')",
            name="ck_meeting_series_cadence",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("resources.id"),
        nullable=True,
    )

    cadence: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    interval: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    occurrence_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Read-only convenience for MeetingSeriesResponse - the actual
    # occurrences are ordinary Meeting rows (series_id + series_sequence),
    # created individually via MeetingService.create_meeting, not
    # written through this relationship.
    meetings: Mapped[list["Meeting"]] = relationship(
        "Meeting",
        lazy="selectin",
        order_by="Meeting.series_sequence",
        viewonly=True,
    )
