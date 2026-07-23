import json
import logging

import requests
from pywebpush import WebPushException, webpush
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Bounded so an unreachable/slow push service can never stall a
# request indefinitely - mirrors WHATSAPP_TIMEOUT_SECONDS.
PUSH_TIMEOUT_SECONDS = 10


def _is_transient_push_error(exc: BaseException) -> bool:
    """
    True only for a transport-level failure (connection refused/reset,
    timed out) or a 5xx from the push service - never a 404/410
    (subscription expired) or 401/403 (VAPID key mismatch), which mean
    the request reached the push service and was rejected for a reason
    retrying can't fix. Mirrors GoogleCalendarService._refresh_with_retry.
    """
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, WebPushException) and exc.response is not None:
        return exc.response.status_code >= 500
    return False


@retry(
    retry=retry_if_exception(_is_transient_push_error),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
def _webpush_with_retry(
    endpoint: str,
    p256dh_key: str,
    auth_key: str,
    title: str,
    body: str,
) -> None:
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


class PushClient:
    """
    Thin wrapper around the Web Push protocol via pywebpush, which
    handles payload encryption and delivery to whichever push service
    (FCM, Mozilla autopush, etc.) owns the subscription's endpoint.

    Like WhatsAppClient, send_notification never raises - every
    failure (missing VAPID config, network error, an expired/invalid
    subscription, a non-2xx response) is caught and logged here, and
    callers get back (sent, error_detail) instead. This guarantees
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
            _webpush_with_retry(endpoint, p256dh_key, auth_key, title, body)
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
