import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.slack_oauth_state import SlackOAuthState
from app.repositories.slack_oauth_state_repository import (
    SlackOAuthStateRepository,
)

STATE_EXPIRY_MINUTES = 10


class SlackOAuthStateService:

    @staticmethod
    def create_state(db: Session, user_id: int) -> str:
        """
        Generates a cryptographically random, single-use OAuth state
        tied to user_id (server-side only — never embedded in the
        state value itself), persists it with an expiry, and returns
        the opaque state string to hand to Slack.
        """
        SlackOAuthStateRepository.delete_expired_for_user(db, user_id)

        state_value = secrets.token_urlsafe(32)

        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=STATE_EXPIRY_MINUTES
        )

        oauth_state = SlackOAuthState(
            state=state_value,
            user_id=user_id,
            expires_at=expires_at,
        )

        SlackOAuthStateRepository.create(db, oauth_state)

        return state_value

    @staticmethod
    def verify_and_consume_state(db: Session, state_value: str):
        """
        Looks up the state, confirms it exists and hasn't expired,
        then deletes it immediately so it cannot be replayed.
        Returns the associated user_id, or None if the state is
        missing, expired, or was already used.
        """
        oauth_state = SlackOAuthStateRepository.get_by_state(
            db,
            state_value,
        )

        if oauth_state is None:
            return None

        expires_at = oauth_state.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < datetime.now(timezone.utc):
            SlackOAuthStateRepository.delete(db, oauth_state)
            return None

        user_id = oauth_state.user_id

        # Consume now, before any downstream step, so a retried or
        # duplicated callback request can never reuse this state.
        SlackOAuthStateRepository.delete(db, oauth_state)

        return user_id
