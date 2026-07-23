from sqlalchemy.orm import Session

from app.models.zoom_credential import ZoomCredential


class ZoomCredentialRepository:

    @staticmethod
    def get_by_user_id(db: Session, user_id: int):
        return (
            db.query(ZoomCredential)
            .filter(ZoomCredential.user_id == user_id)
            .first()
        )

    @staticmethod
    def create(db: Session, credential: ZoomCredential):
        db.add(credential)
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def update(db: Session, credential: ZoomCredential):
        db.commit()
        db.refresh(credential)
        return credential

    @staticmethod
    def delete(db: Session, credential: ZoomCredential):
        db.delete(credential)
        db.commit()
