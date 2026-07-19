from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SlackCredential(Base):
    __tablename__ = "slack_credentials"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    team_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    team_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Slack user ID of the person who completed OAuth consent
    # (authed_user.id from oauth.v2.access). Slack Notifications V1
    # sends direct messages to this user only - chat.postMessage
    # accepts a user ID directly as `channel`, so no separate
    # conversations.open call or channel-selection UI is needed.
    slack_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    scopes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="slack_credential",
    )
