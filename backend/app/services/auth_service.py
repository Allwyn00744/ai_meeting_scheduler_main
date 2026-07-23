import secrets

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth.hashing import hash_password, verify_password
from app.auth.jwt_handler import create_access_token
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.user import UserCreate, LoginRequest


class AuthService:

    @staticmethod
    def register(db: Session, user: UserCreate):

        existing_user = AuthRepository.get_user_by_email(
            db,
            user.email
        )

        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        db_user = User(
            name=user.name,
            email=user.email,
            hashed_password=hash_password(user.password),
            timezone=user.timezone,
        )

        return AuthRepository.create_user(db, db_user)

    @staticmethod
    def login(db: Session, credentials: LoginRequest):

        user = AuthRepository.get_user_by_email(
            db,
            credentials.email
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if not verify_password(
            credentials.password,
            user.hashed_password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        access_token = create_access_token(
            {
                "user_id": user.id,
                "email": user.email
            }
        )

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }

    @staticmethod
    def login_or_register_via_google(
        db: Session,
        email: str,
        name: str,
    ) -> dict:
        """
        Used by GET /auth/google/callback once Google's id_token has
        already been verified (see app/api/auth_routes.py) - email is
        trusted as verified at that point. Finds the existing user by
        email, or creates one on first sign-in. A Google-created user
        still needs *some* value in hashed_password (NOT NULL, see
        User model) even though they'll never use it to log in with a
        password - a random, never-shared value via the same
        hash_password() AuthService.register uses satisfies that
        without a schema change or special-casing the column
        elsewhere.
        """
        user = AuthRepository.get_user_by_email(db, email)

        if user is None:
            user = User(
                name=name,
                email=email,
                hashed_password=hash_password(secrets.token_urlsafe(32)),
                timezone="UTC",
                oauth_provider="google",
            )
            user = AuthRepository.create_user(db, user)

        access_token = create_access_token(
            {
                "user_id": user.id,
                "email": user.email,
            }
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
        }