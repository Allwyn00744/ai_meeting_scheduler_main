from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class NotificationLog(Base):
    """
    Notification Analytics V1: one best-effort row per send attempt
    across all four notification channels. Written by each channel's
    notification service on an independent session, mirroring
    AnalyticsService.try_record_event - a logging failure must never
    affect the (already best-effort) notification send itself.
    """

    __tablename__ = "notification_logs"

    __table_args__ = (
        CheckConstraint(
            "channel IN ('email', 'slack', 'whatsapp', 'push')",
            name="ck_notification_logs_channel",
        ),
        CheckConstraint(
            "event_type IN ('created', 'updated', 'cancelled', 'test')",
            name="ck_notification_logs_event_type",
        ),
        Index(
            "ix_notification_logs_user_id",
            "user_id",
        ),
        Index(
            "ix_notification_logs_created_at",
            "created_at",
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

    meeting_id: Mapped[int | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"),
        nullable=True,
    )

    channel: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    error_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
