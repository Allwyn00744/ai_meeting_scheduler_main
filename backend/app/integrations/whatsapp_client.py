import logging

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# Bounded so an unreachable/slow Meta endpoint can never stall a
# request indefinitely - requests has no default timeout of its own.
WHATSAPP_TIMEOUT_SECONDS = 10

# Transport-level failures only (connection refused/reset, timed out) -
# never a Meta API error body or 4xx (bad token, invalid recipient),
# which means the request reached Meta and was rejected, so retrying
# would just delay the same inevitable failure. Mirrors
# GoogleCalendarService._refresh_with_retry.
_TRANSIENT_REQUEST_ERRORS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


class WhatsAppClient:
    """
    Thin wrapper around the Meta WhatsApp Cloud API's messages endpoint
    (POST https://graph.facebook.com/{API_VERSION}/{PHONE_NUMBER_ID}/messages).

    Unlike SlackAPI, send_text_message never raises - every failure
    (missing config, network error, non-2xx response, an error body)
    is caught and logged here, and callers get back (sent, error_detail)
    instead. This guarantees WhatsAppNotificationService (and,
    transitively, MeetingService) can never be interrupted by a
    WhatsApp outage or misconfiguration.
    """

    @staticmethod
    def send_text_message(phone_number: str, message: str) -> tuple[bool, str | None]:
        """
        Returns (sent, error_detail). error_detail is None on success,
        and otherwise the most specific human-readable reason available
        - Meta's own error message when the API responded with one
        (e.g. "(#131030) Recipient phone number not in allowed list" -
        the near-universal cause of test-message failures while the
        Meta app is still in development mode with an unverified
        business), an HTTP-status-derived message, or the exception
        text as a last resort. Automatic notification callers ignore
        this second element and only look at the bool; the manual
        "send test message" endpoint surfaces it directly so a person
        troubleshooting a Settings-page failure sees the real cause
        instead of a generic "failed to send".
        """
        if not settings.whatsapp_configured:
            logger.warning(
                "WhatsApp Cloud API is not configured; skipping send."
            )
            return False, (
                "WhatsApp isn't configured on the server "
                "(WHATSAPP_ACCESS_TOKEN / WHATSAPP_PHONE_NUMBER_ID missing)."
            )

        url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
            f"/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        )

        try:
            response = _post_with_retry(
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
            )

            body = _safe_json(response)

            # Meta's Graph API can return HTTP 200 with an "error" key
            # in some edge cases (e.g. template/session-window issues),
            # so the status code alone is not a reliable success signal.
            api_error = body.get("error")
            if api_error:
                message_text = api_error.get("message", "Unknown error")
                code = api_error.get("code")
                detail = f"Meta API error{f' ({code})' if code else ''}: {message_text}"
                logger.warning("WhatsApp API returned an error body. error=%s", api_error)
                return False, detail

            response.raise_for_status()
            return True, None
        except requests.HTTPError as exc:
            body = _safe_json(exc.response) if exc.response is not None else {}
            api_error = body.get("error", {})
            message_text = api_error.get("message") or exc.response.text[:200] if exc.response is not None else str(exc)
            logger.exception("Failed to send WhatsApp message (HTTP error).")
            return False, f"Meta API error ({exc.response.status_code if exc.response is not None else '?'}): {message_text}"
        except Exception as exc:
            logger.exception("Failed to send WhatsApp message.")
            return False, f"{type(exc).__name__}: {exc}"


@retry(
    retry=retry_if_exception_type(_TRANSIENT_REQUEST_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    reraise=True,
)
def _post_with_retry(url: str, headers: dict, json: dict) -> requests.Response:
    return requests.post(
        url,
        headers=headers,
        json=json,
        timeout=WHATSAPP_TIMEOUT_SECONDS,
    )


def _safe_json(response: requests.Response) -> dict:
    """
    Normalizes a non-JSON body to a dict with no "error" key, so the
    caller can use a single check regardless of cause.
    """
    try:
        return response.json()
    except ValueError:
        return {}
