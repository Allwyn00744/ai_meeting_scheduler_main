import msal

from app.core.config import settings


class MicrosoftOAuthService:

    # offline_access is requested automatically by MSAL for confidential
    # client apps performing the authorization code / refresh flows (it's
    # what makes a refresh_token come back) - passing it through to MSAL
    # explicitly would just be a redundant reserved scope in the consent
    # request, so it's filtered out here even though it's part of the
    # documented MICROSOFT_SCOPES setting.
    SCOPES = [
        scope
        for scope in settings.microsoft_scopes_list
        if scope != "offline_access"
    ]

    @staticmethod
    def _authority() -> str:
        return (
            f"https://login.microsoftonline.com/"
            f"{settings.MICROSOFT_TENANT_ID}"
        )

    @staticmethod
    def create_client() -> msal.ConfidentialClientApplication:
        return msal.ConfidentialClientApplication(
            client_id=settings.MICROSOFT_CLIENT_ID,
            client_credential=settings.MICROSOFT_CLIENT_SECRET,
            authority=MicrosoftOAuthService._authority(),
        )

    @staticmethod
    def get_authorization_url(state: str) -> str:
        client = MicrosoftOAuthService.create_client()

        return client.get_authorization_request_url(
            scopes=MicrosoftOAuthService.SCOPES,
            state=state,
            redirect_uri=settings.MICROSOFT_REDIRECT_URI,
        )

    @staticmethod
    def exchange_code_for_token(code: str) -> dict:
        client = MicrosoftOAuthService.create_client()

        return client.acquire_token_by_authorization_code(
            code=code,
            scopes=MicrosoftOAuthService.SCOPES,
            redirect_uri=settings.MICROSOFT_REDIRECT_URI,
        )

    @staticmethod
    def refresh_access_token(refresh_token: str) -> dict:
        client = MicrosoftOAuthService.create_client()

        return client.acquire_token_by_refresh_token(
            refresh_token=refresh_token,
            scopes=MicrosoftOAuthService.SCOPES,
        )
