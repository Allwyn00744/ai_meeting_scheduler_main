from datetime import datetime

from sqlalchemy import (
    String,
    Time,
    Boolean,
    DateTime,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Availability(Base):
    __tablename__ = "availability"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    day_of_week: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    start_time: Mapped[datetime.time] = mapped_column(
        Time,
        nullable=False,
    )

    end_time: Mapped[datetime.time] = mapped_column(
        Time,
        nullable=False,
    )

    is_available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )