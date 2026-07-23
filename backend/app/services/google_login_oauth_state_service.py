import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.google_login_oauth_state import GoogleLoginOAuthState
from app.repositories.google_login_oauth_state_repository import (
    GoogleLoginOAuthStateRepository,
)

STATE_EXPIRY_MINUTES = 10


class GoogleLoginOAuthStateService:
    """Mirrors GoogleOAuthStateService exactly, minus the user_id binding - see the model's docstring."""

    @staticmethod
    def create_state(db: Session) -> str:
        GoogleLoginOAuthStateRepository.delete_expired(db)

        state_value = secrets.token_urlsafe(32)

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=STATE_EXPIRY_MINUTES
        )

        oauth_state = GoogleLoginOAuthState(
            state=state_value,
            expires_at=expires_at,
        )

        GoogleLoginOAuthStateRepository.create(db, oauth_state)

        return state_value

    @staticmethod
    def verify_and_consume_state(db: Session, state_value: str) -> bool:
        """
        Returns True if the state was valid and unexpired (and
        consumes it immediately so it cannot be replayed), False
        otherwise.
        """
        oauth_state = GoogleLoginOAuthStateRepository.get_by_state(
            db,
            state_value,
        )

        if oauth_state is None:
            return False

        expires_at = oauth_state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < datetime.now(timezone.utc):
            GoogleLoginOAuthStateRepository.delete(db, oauth_state)
            return False

        GoogleLoginOAuthStateRepository.delete(db, oauth_state)

        return True
