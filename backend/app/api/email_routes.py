from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.email_service import EmailService
from app.services.notification_log_service import NotificationLogService

router = APIRouter(
    prefix="/email",
    tags=["Email"],
)


@router.post("/test")
def send_test_email(
    current_user: User = Depends(get_current_user),
):
    """
    Sends a test email to the authenticated caller's own address, to
    verify SMTP configuration. Previously this endpoint required no
    authentication and always sent to a hardcoded address baked into
    the source code - both of those have been removed.
    """
    try:
        EmailService.send_email(
            to_email=current_user.email,
            subject="AI Meeting Scheduler",
            body="Congratulations! Your email service is working.",
        )
    except Exception as exc:
        NotificationLogService.try_record(
            user_id=current_user.id,
            channel="email",
            event_type="test",
            success=False,
            error_detail=f"{type(exc).__name__}: {exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Failed to send test email. Check SMTP configuration."
            ),
        )

    NotificationLogService.try_record(
        user_id=current_user.id,
        channel="email",
        event_type="test",
        success=True,
    )

    return {
        "message": "Email sent successfully"
    }
