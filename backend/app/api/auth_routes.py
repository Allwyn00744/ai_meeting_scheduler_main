import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.id_token import verify_oauth2_token
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.auth.dependencies import get_current_user
from app.auth.google_login_oauth import GoogleLoginOAuthService
from app.core.config import settings
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.user import (
    UserCreate,
    UserResponse,
    LoginRequest,
    Token,
)
from app.services.auth_service import AuthService
from app.services.google_login_oauth_state_service import (
    GoogleLoginOAuthStateService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
@limiter.limit(settings.AUTH_RATE_LIMIT)
def register(
    request: Request,
    user: UserCreate,
    db: Session = Depends(get_db),
):
    return AuthService.register(db, user)


@router.post(
    "/login",
    response_model=Token,
)
@limiter.limit(settings.AUTH_RATE_LIMIT)
def login(
    request: Request,
    credentials: LoginRequest,
    db: Session = Depends(get_db),
):
    return AuthService.login(db, credentials)
@router.get(
    "/me",
    response_model=UserResponse,
)
def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.get("/google/login")
@limiter.limit(settings.AUTH_RATE_LIMIT)
def google_login(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    "Sign in with Google" - distinct from GET /google/login
    (app/api/google_routes.py), which links an already-logged-in
    user's Calendar. This one requires no auth at all: it's how a
    visitor with no session starts a sign-in.
    """
    state = GoogleLoginOAuthStateService.create_state(db)

    authorization_url = GoogleLoginOAuthService.get_authorization_url(
        state=state,
    )

    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    error_redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/login?google=error"
    )

    error = request.query_params.get("error")
    if error:
        logger.warning(
            "Google login OAuth consent was denied or errored. error=%s",
            error,
        )
        return error_redirect

    state_value = request.query_params.get("state")
    if not state_value:
        logger.warning("Google login OAuth callback missing state.")
        return error_redirect

    if not GoogleLoginOAuthStateService.verify_and_consume_state(
        db,
        state_value,
    ):
        logger.warning(
            "Google login OAuth callback had invalid/expired state."
        )
        return error_redirect

    flow = GoogleLoginOAuthService.create_flow()

    try:
        flow.fetch_token(authorization_response=str(request.url))
    except Exception:
        logger.exception("Google login OAuth token exchange failed.")
        return error_redirect

    try:
        id_info = verify_oauth2_token(
            flow.credentials.id_token,
            GoogleAuthRequest(),
            settings.GOOGLE_CLIENT_ID,
        )
    except Exception:
        logger.exception("Google login id_token verification failed.")
        return error_redirect

    if not id_info.get("email_verified"):
        logger.warning(
            "Google login rejected - email not verified with Google."
        )
        return error_redirect

    token = AuthService.login_or_register_via_google(
        db,
        email=id_info["email"],
        name=id_info.get("name") or id_info["email"].split("@")[0],
    )

    # Unlike the Calendar-connect callback (which redirects to
    # /settings with no token needed, since that flow already has a
    # session), this flow has no JWT until this exact moment - it
    # travels back to the frontend as a URL fragment (#...) rather
    # than a query param so it never lands in server/proxy access
    # logs, and is read client-side by GoogleCallback.tsx.
    return RedirectResponse(
        url=(
            f"{settings.FRONTEND_URL}/auth/google/callback"
            f"#token={token['access_token']}"
        )
    )