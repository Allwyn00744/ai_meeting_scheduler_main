import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.push_client import PushClient
from app.models.meeting import Meeting
from app.models.push_subscription import PushSubscription
from app.repositories.push_subscription_repository import (
    PushSubscriptionRepository,
)
from app.schemas.push import PushSubscribeRequest

logger = logging.getLogger(__name__)


class PushNotificationService:
    """
    Push Notifications V1. Deliberately independent of
    MeetingNotificationService (email), SlackNotificationService, and
    WhatsAppNotificationService - a push delivery outage or
    misconfiguration must never affect any other notification channel,
    Google/Outlook/Teams/Zoom sync, or Meeting Intelligence, and vice
    versa. Notifies only the meeting owner, fanning out to every
    browser/device they've subscribed - unlike Slack/WhatsApp, which
    have exactly one destination per user.
    """

    @staticmethod
    def get_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /push/status. Returns whether this user has any
        enabled push subscription and how many browsers/devices are on
        file (a cheap, read-only check for the Settings UI to render).
        """
        subscriptions = PushSubscriptionRepository.get_by_user_id(
            db,
            user_id,
        )

        return {
            "enabled": any(sub.is_enabled for sub in subscriptions),
            "subscription_count": len(subscriptions),
        }

    @staticmethod
    def subscribe(
        db: Session,
        user_id: int,
        subscribe: PushSubscribeRequest,
    ) -> PushSubscription:
        """
        Used by POST /push/subscribe. Creates a new subscription row on
        first use of a given browser endpoint, or patches the existing
        one - mirrors the existing-vs-create branch in
        WhatsAppNotificationService.update_settings, keyed by endpoint
        instead of user_id since a user may have many subscriptions.
        """
        existing = PushSubscriptionRepository.get_by_endpoint(
            db,
            user_id,
            subscribe.endpoint,
        )

        if existing is None:
            subscription_row = PushSubscription(
                user_id=user_id,
                endpoint=subscribe.endpoint,
                p256dh_key=subscribe.keys.p256dh,
                auth_key=subscribe.keys.auth,
                is_enabled=(
                    subscribe.is_enabled
                    if subscribe.is_enabled is not None
                    else True
                ),
            )
            return PushSubscriptionRepository.create(db, subscription_row)

        existing.p256dh_key = subscribe.keys.p256dh
        existing.auth_key = subscribe.keys.auth

        if subscribe.is_enabled is not None:
            existing.is_enabled = subscribe.is_enabled

        return PushSubscriptionRepository.update(db, existing)

    @staticmethod
    def unsubscribe(db: Session, user_id: int, endpoint: str) -> bool:
        """
        Used by DELETE /push/unsubscribe. Removes the subscription row
        for this browser endpoint, if any.
        """
        existing = PushSubscriptionRepository.get_by_endpoint(
            db,
            user_id,
            endpoint,
        )

        if existing is None:
            return False

        PushSubscriptionRepository.delete(db, existing)
        return True

    @staticmethod
    def _build_payload(event_label: str, meeting: Meeting) -> tuple[str, str]:
        lines = [f"Start: {meeting.start_time}"]

        # Mirrors WhatsAppNotificationService._build_message, which
        # also omits location for a cancellation notice.
        if event_label != "Cancelled":
            lines.append(f"Location: {meeting.location or 'N/A'}")

        title = f"Meeting {event_label}: {meeting.title}"
        return title, "\n".join(lines)

    @staticmethod
    def _send_best_effort(
        db: Session,
        meeting: Meeting,
        event_label: str,
    ) -> bool:
        """
        Never raises - a push delivery outage, missing VAPID
        configuration, or a meeting owner with no enabled subscription
        must not turn an already-persisted meeting operation into a
        failed request, mirroring
        WhatsAppNotificationService._send_best_effort. Fans out to
        every enabled subscription for the owner; returns True if at
        least one delivery succeeded.
        """
        subscriptions = PushSubscriptionRepository.get_enabled_by_user_id(
            db,
            meeting.owner_id,
        )

        if not subscriptions:
            return False

        title, body = PushNotificationService._build_payload(
            event_label,
            meeting,
        )

        sent_any = False
        for subscription_row in subscriptions:
            try:
                if PushClient.send_notification(
                    endpoint=subscription_row.endpoint,
                    p256dh_key=subscription_row.p256dh_key,
                    auth_key=subscription_row.auth_key,
                    title=title,
                    body=body,
                ):
                    sent_any = True
            except Exception:
                logger.exception(
                    "Failed to send push notification. meeting_id=%s "
                    "event=%s subscription_id=%s",
                    meeting.id,
                    event_label,
                    subscription_row.id,
                )

        return sent_any

    @staticmethod
    def notify_meeting_created(db: Session, meeting: Meeting) -> bool:
        return PushNotificationService._send_best_effort(
            db,
            meeting,
            "Created",
        )

    @staticmethod
    def notify_meeting_updated(db: Session, meeting: Meeting) -> bool:
        return PushNotificationService._send_best_effort(
            db,
            meeting,
            "Updated",
        )

    @staticmethod
    def notify_meeting_cancelled(db: Session, meeting: Meeting) -> bool:
        return PushNotificationService._send_best_effort(
            db,
            meeting,
            "Cancelled",
        )

    @staticmethod
    def send_test_notification(db: Session, user_id: int) -> None:
        """
        Used by POST /push/test. Sends a fixed test notification to
        every enabled subscription on file, independent of any meeting
        - lets the Settings UI verify a browser subscription works
        before relying on the automatic notifications. Unlike the
        automatic hooks above, failures here are surfaced to the
        caller rather than swallowed - this is an explicit,
        user-triggered action, mirroring
        WhatsAppNotificationService.send_test_message.
        """
        subscriptions = PushSubscriptionRepository.get_enabled_by_user_id(
            db,
            user_id,
        )

        if not subscriptions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Push notifications are not configured for this user.",
            )

        sent_any = False
        for subscription_row in subscriptions:
            if PushClient.send_notification(
                endpoint=subscription_row.endpoint,
                p256dh_key=subscription_row.p256dh_key,
                auth_key=subscription_row.auth_key,
                title="Test Notification",
                body="This is a test notification from AI Meeting Scheduler.",
            ):
                sent_any = True

        if not sent_any:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to send the push test notification.",
            )
