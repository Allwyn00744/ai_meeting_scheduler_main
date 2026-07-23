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