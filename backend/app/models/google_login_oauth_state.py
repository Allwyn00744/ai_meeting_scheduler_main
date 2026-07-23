from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class GoogleLoginOAuthState(Base):
    """
    CSRF state for the "Sign in with Google" login flow - mirrors
    GoogleOAuthState (app/models/oauth_state.py) used by the existing
    Google Calendar *connect* flow, minus the user_id binding: unlike
    connecting a calendar, a login attempt starts with no authenticated
    user to tie the state to.
    """

    __tablename__ = "google_login_oauth_states"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        index=True,
    )

    state: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
