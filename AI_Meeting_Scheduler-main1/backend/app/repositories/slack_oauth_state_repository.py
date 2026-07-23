from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.slack_oauth_state import SlackOAuthState


class SlackOAuthStateRepository:

    @staticmethod
    def create(db: Session, oauth_state: SlackOAuthState):
        db.add(oauth_state)
        db.commit()
        db.refresh(oauth_state)
        return oauth_state

    @staticmethod
    def get_by_state(db: Session, state: str):
        return (
            db.query(SlackOAuthState)
            .filter(SlackOAuthState.state == state)
            .first()
        )

    @staticmethod
    def delete(db: Session, oauth_state: SlackOAuthState):
        db.delete(oauth_state)
        db.commit()

    @staticmethod
    def delete_expired_for_user(db: Session, user_id: int):
        """
        Housekeeping only: removes stale, unconsumed states for this
        user so the table doesn't accumulate expired rows every time
        someone starts (and abandons) the OAuth flow.
        """
        (
            db.query(SlackOAuthState)
            .filter(
                SlackOAuthState.user_id == user_id,
                SlackOAuthState.expires_at < datetime.now(timezone.utc),
            )
            .delete()
        )
        db.commit()
