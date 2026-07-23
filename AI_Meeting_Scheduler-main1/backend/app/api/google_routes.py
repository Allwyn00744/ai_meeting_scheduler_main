import logging

from fastapi import APIRouter, Request, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.calendar.google_oauth import GoogleOAuthService
from app.auth.dependencies import get_current_user
from app.auth.jwt_handler import verify_access_token
from app.core.config import settings
from app.models.user import User
from app.db.database import get_db
from app.services.google_calendar_service import GoogleCalendarService
from app.services.google_oauth_state_service import GoogleOAuthStateService

logger = logging.getLogger(__name__)

# auto_error=False so /login can also be reached via a plain browser
# navigation (full-page redirect to Google's consent screen), which
# cannot attach an Authorization header. See google_login below.
optional_bearer = HTTPBearer(auto_error=False)

router = APIRouter(
    prefix="/google",
    tags=["Google Calendar"],
)


@router.get("/status")
def google_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return GoogleCalendarService.get_connection_status(
        db,
        current_user.id,
    )


@router.delete("/disconnect")
def google_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    GoogleCalendarService.disconnect(db, current_user.id)
    return {"message": "Google account disconnected successfully"}


@router.get("/login")
def google_login(
    token: str | None = Query(
        default=None,
        description=(
            "Access token, used when this endpoint is reached via a "
            "full-page browser redirect (e.g. window.location = ...) "
            "rather than an XHR/fetch call, since a full-page "
            "navigation cannot attach an Authorization header. API "
            "clients should keep using the header instead."
        ),
    ),
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_bearer),
    db: Session = Depends(get_db),
):
    raw_token = token or (credentials.credentials if credentials else None)

    if raw_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )

    payload = verify_access_token(raw_token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    current_user = (
        db.query(User).filter(User.id == payload["user_id"]).first()
    )

    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    state = GoogleOAuthStateService.create_state(
        db,
        current_user.id,
    )

    authorization_url = GoogleOAuthService.get_authorization_url(
        state=state,
    )

    return RedirectResponse(url=authorization_url)


@router.get("/callback")
def google_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    settings_url = f"{settings.FRONTEND_URL}/settings"
    error_redirect = RedirectResponse(url=f"{settings_url}?google=error")

    error = request.query_params.get("error")

    if error:
        logger.warning(
            "Google OAuth consent was denied or errored. error=%s",
            error,
        )
        return error_redirect

    state_value = request.query_params.get("state")

    if not state_value:
        logger.warning("Google OAuth callback missing state.")
        return error_redirect

    user_id = GoogleOAuthStateService.verify_and_consume_state(
        db,
        state_value,
    )

    if user_id is None:
        logger.warning("Google OAuth callback had invalid/expired state.")
        return error_redirect

    flow = GoogleOAuthService.create_flow()

    try:
        flow.fetch_token(
            authorization_response=str(request.url)
        )
    except Exception:
        logger.exception(
            "Google OAuth token exchange failed. user_id=%s",
            user_id,
        )
        return error_redirect

    credentials = flow.credentials

    GoogleCalendarService.save_google_credentials(
        db=db,
        user_id=user_id,
        credentials=credentials,
    )

    logger.info(
        "Google account connected successfully. user_id=%s",
        user_id,
    )

    return RedirectResponse(url=f"{settings_url}?google=connected")