from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.oauth_state import GoogleOAuthState


class OAuthStateRepository:

    @staticmethod
    def create(db: Session, oauth_state: GoogleOAuthState):
        db.add(oauth_state)
        db.commit()
        db.refresh(oauth_state)
        return oauth_state

    @staticmethod
    def get_by_state(db: Session, state: str):
        return (
            db.query(GoogleOAuthState)
            .filter(GoogleOAuthState.state == state)
            .first()
        )

    @staticmethod
    def delete(db: Session, oauth_state: GoogleOAuthState):
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
            db.query(GoogleOAuthState)
            .filter(
                GoogleOAuthState.user_id == user_id,
                GoogleOAuthState.expires_at < datetime.now(timezone.utc),
            )
            .delete()
        )
        db.commit()