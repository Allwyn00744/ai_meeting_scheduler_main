import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailService:

    @staticmethod
    def send_email(
        to_email: str,
        subject: str,
        body: str,
    ):
        """
        Send an email via SMTP.

        Uses implicit SSL (smtplib.SMTP_SSL, typically port 465) when
        settings.EMAIL_USE_SSL is true, otherwise plaintext + STARTTLS
        (smtplib.SMTP, typically port 587) - the previous behavior,
        which always called starttls() unconditionally and would
        raise on a port-465 SSL-only server.

        Raises the underlying smtplib/OSError exception on failure.
        Callers that trigger email as a side effect of an otherwise
        successful operation (e.g. scheduling a meeting) are
        responsible for catching and handling that so an email outage
        doesn't turn a successful booking into a failed request.
        """

        message = EmailMessage()

        message["Subject"] = subject
        message["From"] = settings.EMAIL_FROM
        message["To"] = to_email

        message.set_content(body)

        if settings.EMAIL_USE_SSL:
            with smtplib.SMTP_SSL(
                settings.EMAIL_HOST,
                settings.EMAIL_PORT,
                timeout=settings.EMAIL_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.login(
                    settings.EMAIL_USERNAME,
                    settings.EMAIL_PASSWORD,
                )
                smtp.send_message(message)
        else:
            with smtplib.SMTP(
                settings.EMAIL_HOST,
                settings.EMAIL_PORT,
                timeout=settings.EMAIL_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.starttls()
                smtp.login(
                    settings.EMAIL_USERNAME,
                    settings.EMAIL_PASSWORD,
                )
                smtp.send_message(message)

    @staticmethod
    def send_meeting_invitation(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
        location: str,
    ):
        body = f"""
    You have been invited to a meeting.

    Title: {meeting_title}

    Start: {start_time}

    End: {end_time}

    Location: {location}

    Please join on time.

    Regards,
    AI Meeting Scheduler
    """

        EmailService.send_email(
            to_email=to_email,
            subject=f"Meeting Invitation: {meeting_title}",
            body=body,
        )

    @staticmethod
    def try_send_meeting_invitation(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
        location: str,
    ) -> bool:
        """
        Best-effort variant for use inside otherwise-successful flows
        (e.g. after a meeting has already been created and committed).
        Never raises - logs and returns False on failure so a broken
        SMTP configuration cannot turn a successful scheduling request
        into a 500 response.
        """
        try:
            EmailService.send_meeting_invitation(
                to_email=to_email,
                meeting_title=meeting_title,
                start_time=start_time,
                end_time=end_time,
                location=location,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send meeting invitation email. "
                "recipient_domain=%s",
                to_email.split("@")[-1] if "@" in to_email else "unknown",
            )
            return False

    @staticmethod
    def send_meeting_update(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
        location: str | None,
    ):
        body = f"""
    A meeting you are part of has been updated.

    Title: {meeting_title}

    New Start: {start_time}

    New End: {end_time}

    Location: {location or "N/A"}

    Please review the updated details.

    Regards,
    AI Meeting Scheduler
    """

        EmailService.send_email(
            to_email=to_email,
            subject=f"Meeting Updated: {meeting_title}",
            body=body,
        )

    @staticmethod
    def try_send_meeting_update(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
        location: str | None,
    ) -> bool:
        """
        Best-effort variant, mirroring try_send_meeting_invitation:
        never raises, so an SMTP outage cannot turn an already-
        persisted meeting update into a failed request.
        """
        try:
            EmailService.send_meeting_update(
                to_email=to_email,
                meeting_title=meeting_title,
                start_time=start_time,
                end_time=end_time,
                location=location,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send meeting update email. "
                "recipient_domain=%s",
                to_email.split("@")[-1] if "@" in to_email else "unknown",
            )
            return False

    @staticmethod
    def send_meeting_cancellation(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
    ):
        body = f"""
    A meeting you were part of has been cancelled.

    Title: {meeting_title}

    Was scheduled: {start_time} - {end_time}

    Regards,
    AI Meeting Scheduler
    """

        EmailService.send_email(
            to_email=to_email,
            subject=f"Meeting Cancelled: {meeting_title}",
            body=body,
        )

    @staticmethod
    def try_send_meeting_cancellation(
        to_email: str,
        meeting_title: str,
        start_time,
        end_time,
    ) -> bool:
        """
        Best-effort variant, mirroring try_send_meeting_invitation:
        never raises, so an SMTP outage cannot turn an already-
        persisted cancellation/deletion into a failed request.
        """
        try:
            EmailService.send_meeting_cancellation(
                to_email=to_email,
                meeting_title=meeting_title,
                start_time=start_time,
                end_time=end_time,
            )
            return True
        except Exception:
            logger.exception(
                "Failed to send meeting cancellation email. "
                "recipient_domain=%s",
                to_email.split("@")[-1] if "@" in to_email else "unknown",
            )
            return False
