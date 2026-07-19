from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

if TYPE_CHECKING:
    from app.models.external_meeting_guest import ExternalMeetingGuest


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    location: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    google_event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    google_meet_link: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    google_event_link: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    outlook_event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    outlook_event_link: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    zoom_meeting_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    zoom_join_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    zoom_start_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Microsoft Teams Integration V1. No teams_meeting_id column exists -
    # a Teams meeting here is not a separate resource, it's the existing
    # Outlook event (outlook_event_id above) with isOnlineMeeting=true /
    # onlineMeetingProvider="teamsForBusiness" set on it, so the event
    # identity is already tracked by outlook_event_id.
    teams_join_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        default="scheduled",
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    resource_id: Mapped[int | None] = mapped_column(
        ForeignKey("resources.id"),
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

    external_guests: Mapped[list["ExternalMeetingGuest"]] = relationship(
        "ExternalMeetingGuest",
        lazy="selectin",
        # "all" (not True) is required here: lazy="selectin" means this
        # collection is eagerly loaded on every Meeting query,
        # including inside MeetingRepository.get_by_id as used by
        # delete_meeting. With plain passive_deletes=True, SQLAlchemy
        # still tries to null out already-loaded children's meeting_id
        # before deleting the parent, which violates the NOT NULL
        # constraint on external_meeting_guests.meeting_id. "all"
        # suppresses that nulling regardless of load state and defers
        # entirely to the database's ON DELETE CASCADE.
        passive_deletes="all",
    )
