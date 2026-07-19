from sqlalchemy.orm import Session

from app.models.google_credential import GoogleCredential


class GoogleCredentialRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(GoogleCredential)
            .filter(GoogleCredential.user_id == user_id)
            .first()
        )

    @staticmethod
    def create(db: Session, credential: GoogleCredential):
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def update(db: Session, credential: GoogleCredential):
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def delete(db: Session, credential: GoogleCredential):
        db.delete(credential)
        db.commit()