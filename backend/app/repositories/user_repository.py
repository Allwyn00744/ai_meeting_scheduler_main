from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserUpdate


class UserRepository:

    @staticmethod
    def get_all_users(db: Session):
        return db.query(User).all()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int):
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_users_by_ids(
        db: Session,
        user_ids: list[int],
    ):
        return (
            db.query(User)
            .filter(User.id.in_(user_ids))
            .all()
        )

    @staticmethod
    def get_user_by_email(db: Session, email: str):
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def get_user_by_email_ci(db: Session, email: str):
        """
        Case-insensitive email lookup. Registered emails are stored
        with whatever casing the user typed at signup (no lowercasing
        normalization exists in AuthService), so a caller resolving
        an externally-supplied or AI-extracted address - which is
        normalized to lowercase before reaching here - must not miss
        a match purely due to stored casing.
        """
        return (
            db.query(User)
            .filter(func.lower(User.email) == email.strip().lower())
            .first()
        )

    @staticmethod
    def update_user(db: Session, user_id: int, user: UserUpdate):

        existing_user = db.query(User).filter(User.id == user_id).first()

        if not existing_user:
            return None

        if user.name is not None:
            existing_user.name = user.name

        if user.email is not None:
            existing_user.email = user.email

        db.commit()
        db.refresh(existing_user)

        return existing_user

    @staticmethod
    def update(db: Session, user: User):
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def delete_user(db: Session, user_id: int):

        existing_user = db.query(User).filter(User.id == user_id).first()

        if not existing_user:
            return None

        db.delete(existing_user)
        db.commit()

        return existing_user
