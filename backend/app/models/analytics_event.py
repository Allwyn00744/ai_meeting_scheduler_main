from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'CONFLICT_BLOCKED_OWNER', "
            "'CONFLICT_BLOCKED_PARTICIPANT', "
            "'CONFLICT_BLOCKED_RESOURCE'"
            ")",
            name="ck_analytics_events_event_type",
        ),
        Index(
            "ix_analytics_events_user_id",
            "user_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
    )

    meeting_id: Mapped[int | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
