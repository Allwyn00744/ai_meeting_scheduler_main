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
    ) -> tuple[bool, str | None]:
        """
        Returns (sent, error_detail). error_detail is None on success,
        and otherwise the most specific reason available - the push
        service's own response body/status (a 404/410 almost always
        means the browser subscription expired or the user uninstalled/
        reset it and needs to re-subscribe; a 401/403 usually means the
        VAPID key pair doesn't match what the browser subscribed with)
        or the exception text as a last resort. Automatic notification
        callers ignore this second element and only look at the bool;
        the manual "send test notification" endpoint surfaces it
        directly.
        """
        if not settings.push_configured:
            logger.warning(
                "Web Push (VAPID) is not configured; skipping send."
            )
            return False, (
                "Push notifications aren't configured on the server "
                "(VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY missing)."
            )

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
            return True, None
        except WebPushException as exc:
            logger.exception("Failed to send push notification.")
            status_code = exc.response.status_code if exc.response is not None else None
            reason = exc.response.text[:200] if exc.response is not None else str(exc)
            hint = ""
            if status_code in (404, 410):
                hint = " (subscription expired - disable and re-enable push in Settings)"
            elif status_code in (401, 403):
                hint = " (VAPID key mismatch - the server's VAPID keys changed since this browser subscribed)"
            return False, f"Push service error{f' ({status_code})' if status_code else ''}: {reason}{hint}"
        except Exception as exc:
            logger.exception("Failed to send push notification.")
            return False, f"{type(exc).__name__}: {exc}"
