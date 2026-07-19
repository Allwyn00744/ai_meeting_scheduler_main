from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column,relationship
from app.db.database import Base

if TYPE_CHECKING:
    from app.models.google_credential import GoogleCredential
    from app.models.outlook_credential import OutlookCredential
    from app.models.zoom_credential import ZoomCredential
    from app.models.slack_credential import SlackCredential
    from app.models.whatsapp_settings import WhatsAppSettings
    from app.models.push_subscription import PushSubscription


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # NEW
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    timezone: Mapped[str] = mapped_column(
        String(100),
        default="UTC",
    )

    oauth_provider: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
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
    google_credential: Mapped["GoogleCredential | None"] = relationship(
        "GoogleCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    outlook_credential: Mapped["OutlookCredential | None"] = relationship(
        "OutlookCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    zoom_credential: Mapped["ZoomCredential | None"] = relationship(
        "ZoomCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    slack_credential: Mapped["SlackCredential | None"] = relationship(
        "SlackCredential",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    whatsapp_settings: Mapped["WhatsAppSettings | None"] = relationship(
        "WhatsAppSettings",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # Push Notifications V1: unlike the single-row integrations above,
    # a user can have many subscriptions (one per browser/device).
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        "PushSubscription",
        back_populates="user",
        cascade="all, delete-orphan",
    )