from sqlalchemy.orm import Session

from app.models.outlook_credential import OutlookCredential


class OutlookCredentialRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(OutlookCredential)
            .filter(OutlookCredential.user_id == user_id)
            .first()
        )

    @staticmethod
    def create(db: Session, credential: OutlookCredential):
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def update(db: Session, credential: OutlookCredential):
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def delete(db: Session, credential: OutlookCredential):
        db.delete(credential)
        db.commit()
