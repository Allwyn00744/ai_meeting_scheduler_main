"""
Integration tests for WhatsApp Notifications V1: the automatic
best-effort hooks in MeetingService.create_meeting/update_meeting/
delete_meeting, plus the manual POST /whatsapp/send/{meeting_id} and
POST /whatsapp/test endpoints. Mirrors the style of
tests/test_slack_notifications.py: a real FastAPI app via starlette's
TestClient, backed by an in-memory SQLite DB.

Meta WhatsApp Cloud API calls are mocked at the WhatsAppClient boundary
(send_text_message) so these tests exercise the real service/
repository/route wiring without making network calls. The
"WhatsApp not enabled" paths are exercised for real, with no mocking
at all - mirrors how the Slack integration tests rely on a real no-op
rather than a patched-out one.

Run with: python -m unittest tests.test_whatsapp_notifications -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402
from app.models.whatsapp_settings import WhatsAppSettings  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

FAKE_PHONE_NUMBER = "+919876543210"


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class WhatsAppNotificationsTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.engine.dispose)

        for event_name in ("load", "refresh"):
            event.listen(Meeting, event_name, _reattach_utc_on_load)
            self.addCleanup(
                event.remove, Meeting, event_name, _reattach_utc_on_load,
            )

        self.client = TestClient(app)

        register_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Owner",
                "email": "owner@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(register_resp.status_code, 201)
        self.owner_id = register_resp.json()["id"]

        login_resp = self.client.post(
            "/auth/login",
            json={
                "email": "owner@example.com",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.json()["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {token}"}

        other_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(other_resp.status_code, 201)
        self.other_user_id = other_resp.json()["id"]

        other_login = self.client.post(
            "/auth/login",
            json={
                "email": "other@example.com",
                "password": "correct horse battery staple",
            },
        )
        other_token = other_login.json()["access_token"]
        self.other_auth_headers = {"Authorization": f"Bearer {other_token}"}

    def _create_meeting(self, headers=None):
        resp = self.client.post(
            "/meetings/",
            json={
                "title": "Standup",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=headers or self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    def _enable_whatsapp(self, user_id: int | None = None):
        """Directly persists an enabled WhatsAppSettings row, bypassing
        PUT /whatsapp/settings itself - that route is covered by
        test_whatsapp_settings.py."""
        db = self.SessionLocal()
        try:
            db.add(
                WhatsAppSettings(
                    user_id=user_id or self.owner_id,
                    phone_number=FAKE_PHONE_NUMBER,
                    is_enabled=True,
                )
            )
            db.commit()
        finally:
            db.close()

    def _create_meeting_whatsapp_muted(self, headers=None):
        """
        Creates a meeting with WhatsApp already enabled, muting the
        automatic create-time WhatsApp call (mocked to succeed but not
        asserted on) so tests focused on a *different* operation don't
        make a real network call as a side effect of setup.
        """
        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ):
            return self._create_meeting(headers=headers)

    # ---- automatic hook: MeetingService.create_meeting ----

    def test_create_meeting_skips_gracefully_when_whatsapp_not_enabled(self):
        # No WhatsAppClient mock at all - if the hook tried a real
        # network call here without a settings short-circuit, this
        # would hang or fail instead of the create succeeding cleanly.
        meeting_id = self._create_meeting()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)

    def test_create_meeting_notifies_whatsapp_when_enabled(self):
        self._enable_whatsapp()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            self._create_meeting()

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["phone_number"], FAKE_PHONE_NUMBER)
        self.assertIn("Meeting Created", mock_send.call_args.kwargs["message"])

    def test_create_meeting_whatsapp_outage_does_not_block_creation(self):
        self._enable_whatsapp()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            side_effect=Exception("boom"),
        ):
            resp = self.client.post(
                "/meetings/",
                json={
                    "title": "Resilient",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                },
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 201)

    def test_create_meeting_skips_when_settings_row_exists_but_disabled(self):
        db = self.SessionLocal()
        try:
            db.add(
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number=FAKE_PHONE_NUMBER,
                    is_enabled=False,
                )
            )
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
        ) as mock_send:
            self._create_meeting()

        mock_send.assert_not_called()

    # ---- automatic hook: MeetingService.update_meeting ----

    def test_update_meeting_notifies_whatsapp_when_enabled(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            resp = self.client.put(
                f"/meetings/{meeting_id}",
                json={"title": "Standup (moved)"},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        self.assertIn("Meeting Updated", mock_send.call_args.kwargs["message"])

    # ---- automatic hook: MeetingService.delete_meeting ----

    def test_delete_meeting_notifies_whatsapp_when_enabled(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        self.assertIn("Meeting Cancelled", mock_send.call_args.kwargs["message"])
        # Cancellation messages omit location - see
        # WhatsAppNotificationService._build_message.
        self.assertNotIn("Location", mock_send.call_args.kwargs["message"])

    def test_delete_meeting_whatsapp_outage_does_not_block_deletion(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            side_effect=Exception("boom"),
        ):
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)

    # ---- manual send: POST /whatsapp/send/{meeting_id} ----

    def test_manual_send_requires_whatsapp_configured(self):
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/whatsapp/send/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_send_success(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            response = self.client.post(
                f"/whatsapp/send/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sent successfully", response.json()["message"])
        mock_send.assert_called_once()

    def test_manual_send_with_custom_message(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            response = self.client.post(
                f"/whatsapp/send/{meeting_id}",
                json={"message": "Custom reminder text"},
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_send.call_args.kwargs["message"], "Custom reminder text")

    def test_manual_send_meeting_not_found(self):
        self._enable_whatsapp()

        response = self.client.post(
            "/whatsapp/send/999999",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_send_unauthorized_wrong_owner(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        response = self.client.post(
            f"/whatsapp/send/{meeting_id}",
            headers=self.other_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_manual_send_no_token_unauthorized(self):
        meeting_id = self._create_meeting()
        response = self.client.post(f"/whatsapp/send/{meeting_id}")
        self.assertEqual(response.status_code, 401)

    def test_manual_send_whatsapp_failure_returns_502(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=False,
        ):
            response = self.client.post(
                f"/whatsapp/send/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 502)

    def test_manual_send_content_matches_automatic_notification_shape(self):
        self._enable_whatsapp()
        meeting_id = self._create_meeting_whatsapp_muted()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            self.client.post(
                f"/whatsapp/send/{meeting_id}",
                headers=self.auth_headers,
            )

        text = mock_send.call_args.kwargs["message"]
        self.assertIn("Standup", text)
        self.assertIn("Start:", text)
        self.assertIn("End:", text)
        self.assertIn("Location:", text)

    # ---- manual test message: POST /whatsapp/test ----

    def test_send_test_notification_requires_phone_number(self):
        response = self.client.post(
            "/whatsapp/test",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_send_test_notification_success(self):
        self._enable_whatsapp()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            response = self.client.post(
                "/whatsapp/test",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["phone_number"], FAKE_PHONE_NUMBER)

    # ---- independence from other providers ----

    def test_whatsapp_notification_does_not_require_other_providers(self):
        """
        WhatsApp Notifications V1 must work with no Google/Outlook/
        Teams/Zoom/Slack connection at all - independence is the whole
        point.
        """
        self._enable_whatsapp()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=True,
        ) as mock_send:
            meeting_id = self._create_meeting()

        mock_send.assert_called_once()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        body = get_resp.json()
        self.assertIsNone(body["zoom_meeting_id"])
        self.assertIsNone(body["teams_join_url"])


if __name__ == "__main__":
    unittest.main()
