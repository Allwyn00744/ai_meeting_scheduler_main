from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.auth.hashing import hash_password

from app.schemas.user import UserUpdate
from app.repositories.user_repository import UserRepository
from app.repositories.meeting_repository import MeetingRepository


class UserService:
    """
    Note: user creation lives exclusively in AuthService.register
    (used by POST /auth/register). There is intentionally no
    UserService.create_user — a previous version of this method built
    a User() without a hashed_password, which violated the NOT NULL
    constraint on that column and was never reachable from any route.
    """

    @staticmethod
    def get_all_users(db: Session):

        return UserRepository.get_all_users(db)

    @staticmethod
    def get_user_by_id(db: Session, user_id: int):

        user = UserRepository.get_user_by_id(db, user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        return user

    @staticmethod
    def update_user(db: Session, user_id: int, user: UserUpdate):

        existing_user = UserRepository.get_user_by_id(db, user_id)

        if not existing_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        if user.email:

            email_exists = UserRepository.get_user_by_email(db, user.email)

            if email_exists and email_exists.id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already exists."
                )

        return UserRepository.update_user(db, user_id, user)

    @staticmethod
    def update_password(
        db: Session,
        user_id: int,
        password: str,
    ):
        user = UserRepository.get_user_by_id(db, user_id)

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found",
            )

        user.hashed_password = hash_password(password)

        return UserRepository.update(db, user)

    @staticmethod
    def delete_user(db: Session, user_id: int):

        user = UserRepository.get_user_by_id(db, user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        # Deleting a user who still owns meetings is intentionally
        # not cascaded at the database level: cascading it would
        # silently mass-delete other people's meetings/invitations
        # and bypass the Google Calendar cleanup that
        # MeetingService.delete_meeting performs. Require the caller
        # to delete/reassign owned meetings first.
        owned_meetings = MeetingRepository.get_user_meetings(
            db,
            user_id,
        )

        if owned_meetings:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete this user while they still own "
                    f"{len(owned_meetings)} meeting(s). Delete or "
                    f"reassign those meetings first."
                ),
            )

        # Any rows where this user is only a participant (not owner)
        # are removed automatically at the database level (ON DELETE
        # CASCADE on meeting_participants.user_id).
        try:
            return UserRepository.delete_user(db, user_id)
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Unable to delete user due to related records. "
                    "Please try again or contact support."
                ),
            )
