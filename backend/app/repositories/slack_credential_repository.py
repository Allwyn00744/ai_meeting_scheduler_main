from sqlalchemy.orm import Session

from app.models.slack_credential import SlackCredential


class SlackCredentialRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(SlackCredential)
            .filter(SlackCredential.user_id == user_id)
            .first()
        )

    @staticmethod
    def create(db: Session, credential: SlackCredential):
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def update(db: Session, credential: SlackCredential):
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def delete(db: Session, credential: SlackCredential):
        db.delete(credential)
        db.commit()
