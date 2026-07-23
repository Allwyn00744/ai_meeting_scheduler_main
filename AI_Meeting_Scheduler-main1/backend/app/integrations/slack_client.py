from urllib.parse import urlencode

import requests

from app.core.config import settings
from app.models.slack_credential import SlackCredential

SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

# Bounded so an unreachable/slow Slack endpoint can never stall a
# request indefinitely - requests has no default timeout of its own.
SLACK_TIMEOUT_SECONDS = 10


class SlackAPIError(Exception):
    """
    Raised when Slack responds with HTTP 200 but {"ok": false, ...} -
    unlike Zoom/Outlook, Slack's Web API reports failures in the JSON
    body rather than the HTTP status code, so response.raise_for_status()
    alone would never catch them.
    """


class SlackOAuthService:
    """
    Slack's OAuth v2 ("Add to Slack") flow, implemented directly
    against Slack's REST endpoints via `requests` - like
    ZoomOAuthService, Slack has no official first-party Python OAuth
    library for this minimal a use case, so this mirrors the same
    build-the-consent-URL / exchange-code-for-token shape.
    """

    @staticmethod
    def get_authorization_url(state: str) -> str:
        params = {
            "client_id": settings.SLACK_CLIENT_ID,
            "redirect_uri": settings.SLACK_REDIRECT_URI,
            "state": state,
        }

        scopes = ",".join(settings.slack_scopes_list)
        if scopes:
            params["scope"] = scopes

        return f"{SLACK_AUTHORIZE_URL}?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_token(code: str) -> dict:
        response = requests.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": settings.SLACK_REDIRECT_URI,
            },
            timeout=SLACK_TIMEOUT_SECONDS,
        )
        return _safe_json(response)


class SlackAPI:
    """
    Slack Notifications V1 only ever sends a direct message to the
    Slack user who authorized the app (see
    SlackCredential.slack_user_id) - chat.postMessage accepts a user ID
    directly as `channel` and Slack opens/reuses the DM automatically,
    so no conversations.open call or channel-selection UI is needed.
    """

    @staticmethod
    def post_message(credential: SlackCredential, text: str) -> dict:
        response = requests.post(
            SLACK_POST_MESSAGE_URL,
            headers={
                "Authorization": f"Bearer {credential.access_token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={
                "channel": credential.slack_user_id,
                "text": text,
            },
            timeout=SLACK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        body = _safe_json(response)

        # Slack's Web API always returns HTTP 200 for well-formed
        # requests, even on failure (e.g. revoked token, bad user id) -
        # the real result is in the "ok" field, so raise_for_status()
        # above cannot detect these on its own.
        if not body.get("ok"):
            raise SlackAPIError(body.get("error", "unknown_error"))

        return body


def _safe_json(response: requests.Response) -> dict:
    """
    Normalizes a non-JSON body (e.g. an infrastructure-level failure)
    to a dict with no "ok"/"access_token" key, so callers can use a
    single check regardless of cause.
    """
    try:
        return response.json()
    except ValueError:
        return {
            "ok": False,
            "error": "invalid_response",
            "status_code": response.status_code,
        }
