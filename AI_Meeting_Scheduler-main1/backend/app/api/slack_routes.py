import logging

from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.integrations.slack_client import SlackOAuthService
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.models.user import User
from app.db.database import get_db
from app.services.meeting_service import MeetingService
from app.services.slack_notification_service import SlackNotificationService
from app.services.slack_oauth_state_service import SlackOAuthStateService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/slack",
    tags=["Slack Notifications"],
)


def _require_slack_configured() -> None:
    if not settings.slack_oauth_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack Notifications integration is not configured.",
        )


@router.get("/status")
def slack_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return SlackNotificationService.get_connection_status(
        db,
        current_user.id,
    )


@router.delete("/disconnect")
def slack_disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    SlackNotificationService.disconnect(db, current_user.id)
    return {"message": "Slack account disconnected successfully"}


@router.post("/connect")
def slack_connect(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns the Slack consent screen URL as JSON rather than
    redirecting directly - same reasoning as Zoom/Outlook's POST
    /connect: this is a normal authenticated fetch call, and the
    frontend performs the actual page navigation itself, which avoids
    ever putting the JWT in a URL/query string.
    """
    _require_slack_configured()

    state = SlackOAuthStateService.create_state(
        db,
        current_user.id,
    )

    authorization_url = SlackOAuthService.get_authorization_url(
        state=state,
    )

    return {"authorization_url": authorization_url}


@router.get("/callback")
def slack_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    settings_url = f"{settings.FRONTEND_URL}/settings"
    error_redirect = RedirectResponse(url=f"{settings_url}?slack=error")

    error = request.query_params.get("error")

    if error:
        logger.warning(
            "Slack OAuth consent was denied or errored. error=%s",
            error,
        )
        return error_redirect

    state_value = request.query_params.get("state")

    if not state_value:
        logger.warning("Slack OAuth callback missing state.")
        return error_redirect

    user_id = SlackOAuthStateService.verify_and_consume_state(
        db,
        state_value,
    )

    if user_id is None:
        logger.warning("Slack OAuth callback had invalid/expired state.")
        return error_redirect

    code = request.query_params.get("code")

    if not code:
        logger.warning(
            "Slack OAuth callback missing code. user_id=%s",
            user_id,
        )
        return error_redirect

    token_response = SlackOAuthService.exchange_code_for_token(code)

    if (
        not token_response.get("ok")
        or "access_token" not in token_response
    ):
        logger.warning(
            "Slack OAuth token exchange failed. user_id=%s error=%s",
            user_id,
            token_response.get("error"),
        )
        return error_redirect

    SlackNotificationService.save_slack_credentials(
        db=db,
        user_id=user_id,
        token_response=token_response,
    )

    logger.info(
        "Slack account connected successfully. user_id=%s",
        user_id,
    )

    return RedirectResponse(url=f"{settings_url}?slack=connected")


@router.post("/send/{meeting_id}")
def send_slack_notification(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return MeetingService.send_slack_notification(
        db,
        meeting_id,
        current_user,
    )
