import logging

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.calendar.zoom_oauth import ZoomOAuthService
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.db.database import get_db
from app.services.meeting_service import MeetingService
from app.services.zoom_calendar_service import ZoomCalendarService
from app.services.zoom_oauth_state_service import ZoomOAuthStateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/zoom",
    tags=["Zoom Meetings"],
)


def _require_zoom_configured() -> None:
    if not settings.zoom_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Zoom Meeting integration is not configured.",
        )


@router.get("/status")
def zoom_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ZoomCalendarService.get_connection_status(
        db,
        current_user.id,
    )


@router.delete("/disconnect")
def zoom_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ZoomCalendarService.disconnect(db, current_user.id)
    return {"message": "Zoom account disconnected successfully"}


@router.post("/connect")
def zoom_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the Zoom consent screen URL as JSON rather than redirecting
    directly - same reasoning as Outlook's POST /outlook/connect: this
    is a normal authenticated fetch call, and the frontend performs the
    actual page navigation itself, which avoids ever putting the JWT
    in a URL/query string.
    """
    _require_zoom_configured()

    state = ZoomOAuthStateService.create_state(
        db,
        current_user.id,
    )

    authorization_url = ZoomOAuthService.get_authorization_url(
        state=state,
    )

    print("\n========== ZOOM AUTH URL ==========")
    print(authorization_url)
    print("===================================\n")

    return {"authorization_url": authorization_url}


@router.get("/callback")
def zoom_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    settings_url = f"{settings.FRONTEND_URL}/settings"
    error_redirect = RedirectResponse(url=f"{settings_url}?zoom=error")

    error = request.query_params.get("error")

    if error:
        logger.warning(
            "Zoom OAuth consent was denied or errored. error=%s",
            error,
        )
        return error_redirect

    state_value = request.query_params.get("state")

    if not state_value:
        logger.warning("Zoom OAuth callback missing state.")
        return error_redirect

    user_id = ZoomOAuthStateService.verify_and_consume_state(
        db,
        state_value,
    )

    if user_id is None:
        logger.warning("Zoom OAuth callback had invalid/expired state.")
        return error_redirect

    code = request.query_params.get("code")

    if not code:
        logger.warning("Zoom OAuth callback missing code. user_id=%s", user_id)
        return error_redirect

    token_response = ZoomOAuthService.exchange_code_for_token(code)

    if "error" in token_response or "access_token" not in token_response:
        logger.warning(
            "Zoom OAuth token exchange failed. user_id=%s error=%s",
            user_id,
            token_response.get("error"),
        )
        return error_redirect

    ZoomCalendarService.save_zoom_credentials(
        db=db,
        user_id=user_id,
        token_response=token_response,
    )

    logger.info(
        "Zoom account connected successfully. user_id=%s",
        user_id,
    )

    return RedirectResponse(url=f"{settings_url}?zoom=connected")


@router.post("/sync/{meeting_id}")
def sync_meeting_to_zoom(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.create_zoom_sync(
        db,
        meeting_id,
        current_user,
    )


@router.put("/sync/{meeting_id}")
def update_zoom_sync(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.update_zoom_sync(
        db,
        meeting_id,
        current_user,
    )


@router.delete("/sync/{meeting_id}")
def delete_zoom_sync(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.delete_zoom_sync(
        db,
        meeting_id,
        current_user,
    )
