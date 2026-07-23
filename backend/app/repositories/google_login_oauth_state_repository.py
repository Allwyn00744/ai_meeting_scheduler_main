from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.google_login_oauth_state import GoogleLoginOAuthState


class GoogleLoginOAuthStateRepository:

    @staticmethod
    def create(db: Session, oauth_state: GoogleLoginOAuthState):
        db.add(oauth_state)
        db.commit()
        db.refresh(oauth_state)
        return oauth_state

    @staticmethod
    def get_by_state(db: Session, state: str):
        return (
            db.query(GoogleLoginOAuthState)
            .filter(GoogleLoginOAuthState.state == state)
            .first()
        )

    @staticmethod
    def delete(db: Session, oauth_state: GoogleLoginOAuthState):
        db.delete(oauth_state)
        db.commit()

    @staticmethod
    def delete_expired(db: Session) -> None:
        """
        Housekeeping only: removes stale, unconsumed login states so
        the table doesn't accumulate rows from abandoned sign-in
        attempts. There's no user to scope this to (unlike
        OAuthStateRepository.delete_expired_for_user) since this flow
        starts anonymous - run unconditionally on each new attempt.
        """
        (
            db.query(GoogleLoginOAuthState)
            .filter(GoogleLoginOAuthState.expires_at < datetime.now(timezone.utc))
            .delete()
        )
        db.commit()
