import os

from google_auth_oauthlib.flow import Flow

from app.core.config import settings

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


class GoogleLoginOAuthService:
    """
    "Sign in with Google" - deliberately separate from
    app/calendar/google_oauth.py's GoogleOAuthService, which is the
    existing Google *Calendar* connect flow (calendar.events scope
    only, tied to an already-logged-in user via
    GoogleOAuthStateService's user_id-bound state). This flow starts
    anonymous and needs an identity (verified email), not calendar
    access, so it requests openid/email/profile instead and uses its
    own redirect URI (GOOGLE_LOGIN_REDIRECT_URI) so Google routes the
    callback here rather than to the Calendar flow's endpoint. Reuses
    the same GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET - one OAuth client
    can have multiple registered redirect URIs.
    """

    SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    @staticmethod
    def create_flow() -> Flow:
        return Flow.from_client_config(
            client_config={
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [
                        settings.GOOGLE_LOGIN_REDIRECT_URI,
                    ],
                }
            },
            scopes=GoogleLoginOAuthService.SCOPES,
            redirect_uri=settings.GOOGLE_LOGIN_REDIRECT_URI,
            autogenerate_code_verifier=False,
        )

    @staticmethod
    def get_authorization_url(state: str) -> str:
        flow = GoogleLoginOAuthService.create_flow()

        authorization_url, _ = flow.authorization_url(
            access_type="online",
            include_granted_scopes="false",
            prompt="select_account",
            state=state,
        )

        return authorization_url
