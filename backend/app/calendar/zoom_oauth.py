import base64
from urllib.parse import urlencode

import requests

from app.core.config import settings

ZOOM_AUTHORIZE_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"

# Bounded so an unreachable/slow Zoom OAuth endpoint can never stall a
# request indefinitely - requests has no default timeout of its own.
ZOOM_TIMEOUT_SECONDS = 10


class ZoomOAuthService:
    """
    Zoom's Authorization Code OAuth flow, implemented directly against
    Zoom's REST endpoints via `requests` rather than a provider SDK -
    unlike Google (google-auth-oauthlib) and Microsoft (msal), Zoom has
    no official first-party Python OAuth library, so this mirrors what
    those libraries do internally: build the consent URL, and exchange
    /refresh tokens via HTTP Basic Auth (client_id:client_secret) at
    Zoom's /oauth/token endpoint. No new dependency is required -
    `requests` is already used by OutlookCalendarAPI.
    """

    @staticmethod
    def _basic_auth_header() -> dict:
        raw = f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode()
        return {"Authorization": f"Basic {base64.b64encode(raw).decode()}"}

    @staticmethod
    def get_authorization_url(state: str) -> str:
        params = {
            "response_type": "code",
            "client_id": settings.ZOOM_CLIENT_ID,
            "redirect_uri": settings.ZOOM_REDIRECT_URI,
            "state": state,
        }

        scopes = " ".join(settings.zoom_scopes_list)
        if scopes:
            params["scope"] = scopes

        return f"{ZOOM_AUTHORIZE_URL}?{urlencode(params)}"

    @staticmethod
    def exchange_code_for_token(code: str) -> dict:
        response = requests.post(
            ZOOM_TOKEN_URL,
            headers={
                **ZoomOAuthService._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.ZOOM_REDIRECT_URI,
            },
            timeout=ZOOM_TIMEOUT_SECONDS,
        )
        return _safe_json(response)

    @staticmethod
    def refresh_access_token(refresh_token: str) -> dict:
        response = requests.post(
            ZOOM_TOKEN_URL,
            headers={
                **ZoomOAuthService._basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=ZOOM_TIMEOUT_SECONDS,
        )
        return _safe_json(response)


def _safe_json(response: requests.Response) -> dict:
    """
    Unlike MSAL (which never raises on OAuth errors and always hands
    back a dict), a raw HTTP call to Zoom's /oauth/token can return a
    non-JSON body on an infrastructure-level failure. Normalize that
    case to a dict with no "access_token" key so callers can keep using
    the same "error" in response or "access_token" not in response
    check regardless of provider.
    """
    try:
        return response.json()
    except ValueError:
        return {"error": "invalid_response", "status_code": response.status_code}
