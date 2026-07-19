import os
from google_auth_oauthlib.flow import Flow

from app.core.config import settings

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

class GoogleOAuthService:

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.events",
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
                        settings.GOOGLE_REDIRECT_URI,
                    ],
                }
            },
            scopes=GoogleOAuthService.SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            autogenerate_code_verifier=False,
        )

    @staticmethod
    def get_authorization_url(state: str) -> str:
        flow = GoogleOAuthService.create_flow()

        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )

        return authorization_url