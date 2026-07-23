from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AI Meeting Scheduler"
    APP_VERSION: str = "1.0.0"

    DATABASE_URL: str

    # Set to true only for local debugging. Logs every SQL statement
    # (including bound parameter values), which is noisy and can leak
    # sensitive data into logs/console output if left on in production.
    SQLALCHEMY_ECHO: bool = False

    EMAIL_HOST: str
    EMAIL_PORT: int
    EMAIL_USERNAME: str
    EMAIL_PASSWORD: str
    EMAIL_FROM: str

    # If true, connect using implicit SSL (typically port 465) via
    # smtplib.SMTP_SSL instead of plaintext + STARTTLS (typically
    # port 587). Defaults to STARTTLS since that's what the provider
    # this app was built against (Gmail SMTP, port 587) expects.
    EMAIL_USE_SSL: bool = False
    EMAIL_TIMEOUT_SECONDS: int = 10

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str

    # Where the Google OAuth callback sends the browser after it
    # finishes (success or error) - the frontend's Settings page, not
    # this API. Never include a trailing slash.
    FRONTEND_URL: str = "http://localhost:5173"

    # Microsoft OAuth (Outlook Calendar)
    # Optional, like GEMINI_API_KEY below: /outlook endpoints return 503
    # when absent or blank, so environments that don't need Outlook
    # integration are not required to touch .env for this app to start.
    # Register an app at https://portal.azure.com (Azure AD App
    # registrations) to obtain these.
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/outlook/callback"

    # "common" allows both work/school and personal Microsoft accounts
    # to sign in, matching this app's Google integration which is not
    # restricted to a single Google Workspace domain either.
    MICROSOFT_TENANT_ID: str = "common"

    # OnlineMeetings.ReadWrite was added for Microsoft Teams Integration
    # V1 (teams_meeting_service.py sets isOnlineMeeting/onlineMeetingProvider
    # on Outlook calendar events). Users who connected Outlook before this
    # scope was added hold a token without it - TeamsMeetingService detects
    # the resulting Graph 403 and asks them to reconnect rather than
    # failing silently or forcing a redundant OAuth flow for everyone.
    MICROSOFT_SCOPES: str = (
        "https://graph.microsoft.com/Calendars.ReadWrite "
        "https://graph.microsoft.com/OnlineMeetings.ReadWrite "
        "offline_access"
    )

    # JWT
    # No default on purpose: the application must fail fast at
    # startup if this is not supplied via environment/.env, rather
    # than silently falling back to a value baked into source control.
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Comma-separated list of allowed frontend origins for CORS, e.g.
    # "http://localhost:3000,https://app.example.com". Never include
    # "*" here — a wildcard origin combined with credentialed
    # requests (cookies/Authorization headers) is rejected by
    # browsers anyway and is not a safe configuration.
    CORS_ORIGINS: str = "http://localhost:3000"

    # Default page size / max page size for list endpoints that
    # support pagination.
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE: int = 200

    # Gemini AI
    # Optional: AI endpoints return 503 when absent or blank.
    # Obtain a key from https://aistudio.google.com/apikey
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Redis cache (optional). Redis is optional infrastructure: when
    # REDIS_URL is unset, blank, or unreachable, caching is silently
    # disabled and every read falls back to PostgreSQL - this is a
    # supported production configuration, not a degraded one.
    REDIS_URL: Optional[str] = None

    # Bounded so a slow/unreachable Redis can never stall a request
    # for long before falling back to PostgreSQL.
    REDIS_SOCKET_TIMEOUT_SECONDS: float = 2.0
    REDIS_CONNECT_TIMEOUT_SECONDS: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]
        # Defensively strip any wildcard that might get configured -
        # this app always sends credentials (Authorization headers),
        # and a wildcard origin must never be combined with that.
        return [origin for origin in origins if origin != "*"]

    @property
    def gemini_api_key_configured(self) -> bool:
        """True only when GEMINI_API_KEY is set and non-blank."""
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip())

    @property
    def microsoft_scopes_list(self) -> list[str]:
        return [
            scope.strip()
            for scope in self.MICROSOFT_SCOPES.split(" ")
            if scope.strip()
        ]

    @property
    def microsoft_oauth_configured(self) -> bool:
        """True only when both Microsoft OAuth credentials are set."""
        return bool(
            self.MICROSOFT_CLIENT_ID
            and self.MICROSOFT_CLIENT_ID.strip()
            and self.MICROSOFT_CLIENT_SECRET
            and self.MICROSOFT_CLIENT_SECRET.strip()
        )

    # Zoom OAuth (Zoom Meetings)
    # Optional, like MICROSOFT_CLIENT_ID above: /zoom endpoints return
    # 503 when absent or blank. Register an OAuth app (type: "User-
    # managed app" / Authorization Code Grant) at
    # https://marketplace.zoom.us/develop/create to obtain these.
    ZOOM_CLIENT_ID: Optional[str] = None
    ZOOM_CLIENT_SECRET: Optional[str] = None
    ZOOM_REDIRECT_URI: str = "http://localhost:8000/zoom/callback"

    ZOOM_SCOPES: str = "meeting:write:meeting meeting:read:meeting user:read:user"

    @property
    def zoom_scopes_list(self) -> list[str]:
        return [
            scope.strip()
            for scope in self.ZOOM_SCOPES.split(" ")
            if scope.strip()
        ]

    @property
    def zoom_oauth_configured(self) -> bool:
        """True only when both Zoom OAuth credentials are set."""
        return bool(
            self.ZOOM_CLIENT_ID
            and self.ZOOM_CLIENT_ID.strip()
            and self.ZOOM_CLIENT_SECRET
            and self.ZOOM_CLIENT_SECRET.strip()
        )

    # Slack OAuth (Slack Notifications)
    # Optional, like ZOOM_CLIENT_ID above: /slack endpoints return 503
    # when absent or blank. Create a Slack app (OAuth & Permissions ->
    # Bot Token Scopes) at https://api.slack.com/apps to obtain these.
    SLACK_CLIENT_ID: Optional[str] = None
    SLACK_CLIENT_SECRET: Optional[str] = None
    SLACK_REDIRECT_URI: str = "http://localhost:8000/slack/callback"

    # chat:write is the only bot scope Slack Notifications V1 needs -
    # chat.postMessage accepts a Slack user ID directly as the
    # `channel` parameter to DM that user, with no separate
    # conversations.open call or additional im:write scope required.
    SLACK_SCOPES: str = "chat:write"

    @property
    def slack_scopes_list(self) -> list[str]:
        return [
            scope.strip()
            for scope in self.SLACK_SCOPES.split(" ")
            if scope.strip()
        ]

    @property
    def slack_oauth_configured(self) -> bool:
        """True only when both Slack OAuth credentials are set."""
        return bool(
            self.SLACK_CLIENT_ID
            and self.SLACK_CLIENT_ID.strip()
            and self.SLACK_CLIENT_SECRET
            and self.SLACK_CLIENT_SECRET.strip()
        )

    # WhatsApp Cloud API (Meta) - WhatsApp Notifications
    # Optional, like SLACK_CLIENT_ID above: /whatsapp send/test endpoints
    # return 503 when absent or blank. Create a Meta app with the
    # WhatsApp product added at https://developers.facebook.com/apps to
    # obtain an access token and phone number ID.
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v23.0"

    @property
    def whatsapp_configured(self) -> bool:
        """True only when both WhatsApp Cloud API credentials are set."""
        return bool(
            self.WHATSAPP_ACCESS_TOKEN
            and self.WHATSAPP_ACCESS_TOKEN.strip()
            and self.WHATSAPP_PHONE_NUMBER_ID
            and self.WHATSAPP_PHONE_NUMBER_ID.strip()
        )

    # Web Push / VAPID (Push Notifications)
    # Optional, like WHATSAPP_ACCESS_TOKEN above: PushClient.send_notification
    # returns False when absent or blank. Generate a VAPID key pair with
    # `vapid --gen` (py-vapid, pulled in by pywebpush) to obtain these.
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_CLAIM_EMAIL: str = "admin@example.com"

    @property
    def push_configured(self) -> bool:
        """True only when both VAPID keys are set."""
        return bool(
            self.VAPID_PRIVATE_KEY
            and self.VAPID_PRIVATE_KEY.strip()
            and self.VAPID_PUBLIC_KEY
            and self.VAPID_PUBLIC_KEY.strip()
        )


settings = Settings()
