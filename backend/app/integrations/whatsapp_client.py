import logging

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Bounded so an unreachable/slow Meta endpoint can never stall a
# request indefinitely - requests has no default timeout of its own.
WHATSAPP_TIMEOUT_SECONDS = 10


class WhatsAppClient:
    """
    Thin wrapper around the Meta WhatsApp Cloud API's messages endpoint
    (POST https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages).

    Unlike SlackAPI, send_text_message never raises - every failure
    (missing config, network error, non-2xx response, an error body)
    is caught and logged here, and callers get back a plain bool. This
    guarantees WhatsAppNotificationService (and, transitively,
    MeetingService) can never be interrupted by a WhatsApp outage or
    misconfiguration.
    """

    @staticmethod
    def send_text_message(phone_number: str, message: str) -> bool:
        if not settings.whatsapp_configured:
            logger.warning(
                "WhatsApp Cloud API is not configured; skipping send."
            )
            return False

        url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
            f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )

        try:
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": phone_number,
                    "type": "text",
                    "text": {"body": message},
                },
                timeout=WHATSAPP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()

            body = _safe_json(response)

            # Meta's Graph API can return HTTP 200 with an "error" key
            # in some edge cases (e.g. template/session-window issues),
            # so the status code alone is not a reliable success signal.
            if body.get("error"):
                logger.warning(
                    "WhatsApp API returned an error body. error=%s",
                    body.get("error"),
                )
                return False

            return True
        except Exception:
            logger.exception("Failed to send WhatsApp message.")
            return False


def _safe_json(response: requests.Response) -> dict:
    """
    Normalizes a non-JSON body to a dict with no "error" key, so the
    caller can use a single check regardless of cause.
    """
    try:
        return response.json()
    except ValueError:
        return {}
