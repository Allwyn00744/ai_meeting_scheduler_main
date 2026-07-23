"""
Unit tests for the retry-with-backoff wrapper added around each
calendar integration's OAuth token-refresh call (Google, Outlook,
Zoom) - see the `@retry(...)`-decorated helper functions at the top
of app/services/{google,outlook,zoom}_calendar_service.py.

Each provider must retry on a transient transport-level failure and
succeed once the network recovers, but must NOT retry when the
provider rejects the refresh token itself (revoked/expired access) -
that's not a transient condition and retrying would only delay an
inevitable, correctly-surfaced 400.

Run with: python -m unittest tests.test_oauth_token_refresh_retry -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402
from google.auth.exceptions import RefreshError, TransportError  # noqa: E402
from google.oauth2.credentials import Credentials  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.models.google_credential import GoogleCredential  # noqa: E402
from app.models.outlook_credential import OutlookCredential  # noqa: E402
from app.models.zoom_credential import ZoomCredential  # noqa: E402
from app.services.google_calendar_service import GoogleCalendarService  # noqa: E402
from app.services.outlook_calendar_service import OutlookCalendarService  # noqa: E402
from app.services.zoom_calendar_service import ZoomCalendarService  # noqa: E402

PAST = datetime.now(timezone.utc) - timedelta(hours=1)


class OAuthTokenRefreshRetryTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.db = SessionLocal()
        # addCleanup runs LIFO - register dispose first so db.close()
        # (registered second, so it runs first) closes the session
        # before the engine itself is disposed.
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    # ---- Google ----

    def test_google_refresh_retries_transport_error_then_succeeds(self):
        credential = GoogleCredential(
            user_id=1,
            access_token="stale",
            refresh_token="refresh-me",
            token_uri="https://oauth2.googleapis.com/token",
            scopes="https://www.googleapis.com/auth/calendar.events",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        call_count = {"n": 0}

        def flaky_refresh(self, request):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise TransportError("network blip")
            self.token = "fresh-token"
            self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

        with patch.object(Credentials, "refresh", flaky_refresh):
            result = GoogleCalendarService.refresh_google_token(self.db, credential)

        self.assertEqual(call_count["n"], 3)
        self.assertEqual(result.access_token, "fresh-token")

    def test_google_refresh_does_not_retry_refresh_error(self):
        credential = GoogleCredential(
            user_id=1,
            access_token="stale",
            refresh_token="revoked",
            token_uri="https://oauth2.googleapis.com/token",
            scopes="https://www.googleapis.com/auth/calendar.events",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        call_count = {"n": 0}

        def always_revoked(self, request):
            call_count["n"] += 1
            raise RefreshError("invalid_grant")

        with patch.object(Credentials, "refresh", always_revoked):
            with self.assertRaises(HTTPException) as ctx:
                GoogleCalendarService.refresh_google_token(self.db, credential)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(call_count["n"], 1)

    # ---- Outlook ----

    def test_outlook_refresh_retries_request_exception_then_succeeds(self):
        import requests

        credential = OutlookCredential(
            user_id=1,
            access_token="stale",
            refresh_token="refresh-me",
            scopes="Calendars.ReadWrite",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        side_effects = [
            requests.exceptions.ConnectionError("blip"),
            requests.exceptions.ConnectionError("blip"),
            {"access_token": "fresh-token", "expires_in": 3600},
        ]

        with patch(
            "app.services.outlook_calendar_service.MicrosoftOAuthService.refresh_access_token",
            side_effect=side_effects,
        ) as mock_refresh:
            result = OutlookCalendarService.refresh_outlook_token(self.db, credential)

        self.assertEqual(mock_refresh.call_count, 3)
        self.assertEqual(result.access_token, "fresh-token")

    def test_outlook_refresh_does_not_retry_error_response_dict(self):
        credential = OutlookCredential(
            user_id=1,
            access_token="stale",
            refresh_token="revoked",
            scopes="Calendars.ReadWrite",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        with patch(
            "app.services.outlook_calendar_service.MicrosoftOAuthService.refresh_access_token",
            return_value={"error": "invalid_grant"},
        ) as mock_refresh:
            with self.assertRaises(HTTPException) as ctx:
                OutlookCalendarService.refresh_outlook_token(self.db, credential)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(mock_refresh.call_count, 1)

    # ---- Zoom ----

    def test_zoom_refresh_retries_request_exception_then_succeeds(self):
        import requests

        credential = ZoomCredential(
            user_id=1,
            access_token="stale",
            refresh_token="refresh-me",
            scopes="meeting:write:meeting",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        side_effects = [
            requests.exceptions.Timeout("blip"),
            {"access_token": "fresh-token", "expires_in": 3600},
        ]

        with patch(
            "app.services.zoom_calendar_service.ZoomOAuthService.refresh_access_token",
            side_effect=side_effects,
        ) as mock_refresh:
            result = ZoomCalendarService.refresh_zoom_token(self.db, credential)

        self.assertEqual(mock_refresh.call_count, 2)
        self.assertEqual(result.access_token, "fresh-token")

    def test_zoom_refresh_does_not_retry_error_response_dict(self):
        credential = ZoomCredential(
            user_id=1,
            access_token="stale",
            refresh_token="revoked",
            scopes="meeting:write:meeting",
            expiry=PAST,
        )
        self.db.add(credential)
        self.db.commit()

        with patch(
            "app.services.zoom_calendar_service.ZoomOAuthService.refresh_access_token",
            return_value={"error": "invalid_grant"},
        ) as mock_refresh:
            with self.assertRaises(HTTPException) as ctx:
                ZoomCalendarService.refresh_zoom_token(self.db, credential)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(mock_refresh.call_count, 1)


if __name__ == "__main__":
    unittest.main()
