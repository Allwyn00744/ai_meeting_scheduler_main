import json
import logging

from pywebpush import WebPushException, webpush

from app.core.config import settings

logger = logging.getLogger(__name__)

# Bounded so an unreachable/slow push service can never stall a
# request indefinitely - mirrors WHATSAPP_TIMEOUT_SECONDS.
PUSH_TIMEOUT_SECONDS = 10


class PushClient:
    """
    Thin wrapper around the Web Push protocol via pywebpush, which
    handles payload encryption and delivery to whichever push service
    (FCM, Mozilla autopush, etc.) owns the subscription's endpoint.

    Like WhatsAppClient, send_notification never raises - every
    failure (missing VAPID config, network error, an expired/invalid
    subscription, a non-2xx response) is caught and logged here, and
    callers get back a plain bool. This guarantees
    PushNotificationService (and, transitively, MeetingService) can
    never be interrupted by a push delivery outage or misconfiguration.
    """

    @staticmethod
    def send_notification(
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        title: str,
        body: str,
    ) -> bool:
        if not settings.push_configured:
            logger.warning(
                "Web Push (VAPID) is not configured; skipping send."
            )
            return False

        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {
                        "p256dh": p256dh_key,
                        "auth": auth_key,
                    },
                },
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": f"mailto:{settings.VAPID_CLAIM_EMAIL}",
                },
                timeout=PUSH_TIMEOUT_SECONDS,
            )
            return True
        except WebPushException:
            logger.exception("Failed to send push notification.")
            return False
        except Exception:
            logger.exception("Failed to send push notification.")
            return False
