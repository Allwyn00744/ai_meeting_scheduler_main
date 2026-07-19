import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.whatsapp_client import WhatsAppClient
from app.models.meeting import Meeting
from app.models.whatsapp_settings import WhatsAppSettings
from app.repositories.whatsapp_settings_repository import (
    WhatsAppSettingsRepository,
)
from app.schemas.whatsapp import WhatsAppSettingsUpdate

logger = logging.getLogger(__name__)


class WhatsAppNotificationService:
    """
    WhatsApp Notifications V1. Deliberately independent of
    MeetingNotificationService (email) and SlackNotificationService - a
    WhatsApp outage or misconfiguration must never affect email
    delivery, Slack delivery, Google/Outlook/Teams/Zoom sync, or
    Meeting Intelligence, and vice versa. Notifies only the meeting
    owner, via the phone number stored on their own WhatsAppSettings
    row - there is no participant/external-guest fan-out, mirroring
    Slack Notifications V1.
    """

    @staticmethod
    def get_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /whatsapp/status. Returns whether this user has
        WhatsApp notifications enabled and the phone number on file (a
        cheap, read-only check for the Settings UI to render).
        """
        settings_row = WhatsAppSettingsRepository.get_by_user_id(
            db,
            user_id,
        )

        return {
            "enabled": bool(settings_row and settings_row.is_enabled),
            "phone_number": (
                settings_row.phone_number if settings_row else None
            ),
        }

    @staticmethod
    def update_settings(
        db: Session,
        user_id: int,
        update: WhatsAppSettingsUpdate,
    ) -> WhatsAppSettings:
        """
        Used by PUT /whatsapp/settings. Creates the settings row on
        first use, or patches the existing one - mirrors the
        existing-vs-create branch in
        SlackNotificationService.save_slack_credentials.
        """
        settings_row = WhatsAppSettingsRepository.get_by_user_id(
            db,
            user_id,
        )

        if settings_row is None:
            settings_row = WhatsAppSettings(
                user_id=user_id,
                phone_number=update.phone_number,
                is_enabled=(
                    update.is_enabled
                    if update.is_enabled is not None
                    else False
                ),
            )
            return WhatsAppSettingsRepository.create(db, settings_row)

        if update.phone_number is not None:
            settings_row.phone_number = update.phone_number

        if update.is_enabled is not None:
            settings_row.is_enabled = update.is_enabled

        return WhatsAppSettingsRepository.update(db, settings_row)

    @staticmethod
    def _build_message(event_label: str, meeting: Meeting) -> str:
        lines = [
            f"Meeting {event_label}: {meeting.title}",
            f"Start: {meeting.start_time}",
            f"End: {meeting.end_time}",
        ]

        # Mirrors SlackNotificationService._build_message, which also
        # omits location for a cancellation notice.
        if event_label != "Cancelled":
            lines.append(f"Location: {meeting.location or 'N/A'}")

        return "\n".join(lines)

    @staticmethod
    def _get_active_settings(
        db: Session,
        user_id: int,
    ) -> Optional[WhatsAppSettings]:
        settings_row = WhatsAppSettingsRepository.get_by_user_id(
            db,
            user_id,
        )

        if (
            settings_row is None
            or not settings_row.is_enabled
            or not settings_row.phone_number
        ):
            return None

        return settings_row

    @staticmethod
    def _send_best_effort(
        db: Session,
        meeting: Meeting,
        event_label: str,
    ) -> bool:
        """
        Never raises - a WhatsApp outage, missing configuration, or a
        meeting owner who never enabled WhatsApp must not turn an
        already-persisted meeting operation into a failed request,
        mirroring SlackNotificationService._send_best_effort.
        """
        settings_row = WhatsAppNotificationService._get_active_settings(
            db,
            meeting.owner_id,
        )

        if settings_row is None:
            return False

        try:
            return WhatsAppClient.send_text_message(
                phone_number=settings_row.phone_number,
                message=WhatsAppNotificationService._build_message(
                    event_label,
                    meeting,
                ),
            )
        except Exception:
            logger.exception(
                "Failed to send WhatsApp notification. meeting_id=%s "
                "event=%s",
                meeting.id,
                event_label,
            )
            return False

    @staticmethod
    def notify_meeting_created(db: Session, meeting: Meeting) -> bool:
        return WhatsAppNotificationService._send_best_effort(
            db,
            meeting,
            "Created",
        )

    @staticmethod
    def notify_meeting_updated(db: Session, meeting: Meeting) -> bool:
        return WhatsAppNotificationService._send_best_effort(
            db,
            meeting,
            "Updated",
        )

    @staticmethod
    def notify_meeting_cancelled(db: Session, meeting: Meeting) -> bool:
        return WhatsAppNotificationService._send_best_effort(
            db,
            meeting,
            "Cancelled",
        )

    @staticmethod
    def send_manual_notification(
        db: Session,
        meeting: Meeting,
        custom_message: Optional[str] = None,
    ) -> None:
        """
        Used by POST /whatsapp/send/{meeting_id}. Unlike the automatic
        hooks above, failures here are surfaced to the caller rather
        than swallowed - this is an explicit, user-triggered action,
        mirroring SlackNotificationService.send_manual_notification.
        """
        settings_row = WhatsAppSettingsRepository.get_by_user_id(
            db,
            meeting.owner_id,
        )

        if settings_row is None or not settings_row.phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp is not configured for this user.",
            )

        message = custom_message or WhatsAppNotificationService._build_message(
            "Notification",
            meeting,
        )

        sent = WhatsAppClient.send_text_message(
            phone_number=settings_row.phone_number,
            message=message,
        )

        if not sent:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send the WhatsApp notification.",
            )

    @staticmethod
    def send_test_message(db: Session, user_id: int) -> None:
        """
        Used by POST /whatsapp/test. Sends a fixed test message to the
        phone number on file, independent of any meeting - lets the
        Settings UI verify a phone number/token pair works before
        relying on the automatic notifications.
        """
        settings_row = WhatsAppSettingsRepository.get_by_user_id(
            db,
            user_id,
        )

        if settings_row is None or not settings_row.phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WhatsApp phone number is not configured.",
            )

        sent = WhatsAppClient.send_text_message(
            phone_number=settings_row.phone_number,
            message=(
                "This is a test notification from AI Meeting Scheduler."
            ),
        )

        if not sent:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send the WhatsApp test notification.",
            )
