"""
Integration tests for Push Notifications V1: the automatic best-effort
hooks in MeetingService.create_meeting/update_meeting/delete_meeting,
plus the manual POST /push/test endpoint. Mirrors the style of
tests/test_whatsapp_notifications.py: a real FastAPI app via starlette's
TestClient, backed by an in-memory SQLite DB.

Web Push delivery is mocked at the PushClient boundary
(send_notification) so these tests exercise the real service/
repository/route wiring without making network calls. The
"push not enabled" paths are exercised for real, with no mocking at
all - mirrors how the WhatsApp integration tests rely on a real no-op
rather than a patched-out one.

Run with: python -m unittest tests.test_push_notifications -v
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
from app.models.push_subscription import PushSubscription  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

FAKE_ENDPOINT = "https://fcm.googleapis.com/fcm/send/aaa"
FAKE_ENDPOINT_2 = "https://fcm.googleapis.com/fcm/send/bbb"


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class PushNotificationsTestCase(unittest.TestCase):

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

    def _enable_push(self, user_id: int | None = None, endpoint: str = FAKE_ENDPOINT):
        """Directly persists an enabled PushSubscription row, bypassing
        POST /push/subscribe itself - that route is covered by
        test_push_subscriptions.py."""
        db = self.SessionLocal()
        try:
            db.add(
                PushSubscription(
                    user_id=user_id or self.owner_id,
                    endpoint=endpoint,
                    p256dh_key="p256dh-key",
                    auth_key="auth-key",
                    is_enabled=True,
                )
            )
            db.commit()
        finally:
            db.close()

    def _create_meeting_push_muted(self, headers=None):
        """
        Creates a meeting with push already enabled, muting the
        automatic create-time push call (mocked to succeed but not
        asserted on) so tests focused on a *different* operation don't
        make a real network call as a side effect of setup.
        """
        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ):
            return self._create_meeting(headers=headers)

    # ---- automatic hook: MeetingService.create_meeting ----

    def test_create_meeting_skips_gracefully_when_push_not_enabled(self):
        # No PushClient mock at all - if the hook tried a real network
        # call here without a subscription short-circuit, this would
        # hang or fail instead of the create succeeding cleanly.
        meeting_id = self._create_meeting()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)

    def test_create_meeting_notifies_push_when_enabled(self):
        self._enable_push()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ) as mock_send:
            self._create_meeting()

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["endpoint"], FAKE_ENDPOINT)
        self.assertIn("Meeting Created", mock_send.call_args.kwargs["title"])

    def test_create_meeting_notifies_all_subscriptions(self):
        self._enable_push(endpoint=FAKE_ENDPOINT)
        self._enable_push(endpoint=FAKE_ENDPOINT_2)

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ) as mock_send:
            self._create_meeting()

        self.assertEqual(mock_send.call_count, 2)

    def test_create_meeting_push_outage_does_not_block_creation(self):
        self._enable_push()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
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

    def test_create_meeting_skips_when_subscription_disabled(self):
        db = self.SessionLocal()
        try:
            db.add(
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT,
                    p256dh_key="p256dh-key",
                    auth_key="auth-key",
                    is_enabled=False,
                )
            )
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
        ) as mock_send:
            self._create_meeting()

        mock_send.assert_not_called()

    # ---- automatic hook: MeetingService.update_meeting ----

    def test_update_meeting_notifies_push_when_enabled(self):
        self._enable_push()
        meeting_id = self._create_meeting_push_muted()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ) as mock_send:
            resp = self.client.put(
                f"/meetings/{meeting_id}",
                json={"title": "Standup (moved)"},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        self.assertIn("Meeting Updated", mock_send.call_args.kwargs["title"])

    # ---- automatic hook: MeetingService.delete_meeting ----

    def test_delete_meeting_notifies_push_when_enabled(self):
        self._enable_push()
        meeting_id = self._create_meeting_push_muted()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ) as mock_send:
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_send.assert_called_once()
        self.assertIn("Meeting Cancelled", mock_send.call_args.kwargs["title"])
        # Cancellation messages omit location - see
        # PushNotificationService._build_payload.
        self.assertNotIn("Location", mock_send.call_args.kwargs["body"])

    def test_delete_meeting_push_outage_does_not_block_deletion(self):
        self._enable_push()
        meeting_id = self._create_meeting_push_muted()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            side_effect=Exception("boom"),
        ):
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)

    # ---- manual test message: POST /push/test ----

    def test_send_test_notification_requires_subscription(self):
        response = self.client.post(
            "/push/test",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_send_test_notification_success(self):
        self._enable_push()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=True,
        ) as mock_send:
            response = self.client.post(
                "/push/test",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["endpoint"], FAKE_ENDPOINT)

    def test_send_test_notification_failure_returns_502(self):
        self._enable_push()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=False,
        ):
            response = self.client.post(
                "/push/test",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 502)

    def test_send_test_notification_no_token_unauthorized(self):
        response = self.client.post("/push/test")
        self.assertEqual(response.status_code, 401)

    # ---- independence from other providers ----

    def test_push_notification_does_not_require_other_providers(self):
        """
        Push Notifications V1 must work with no Google/Outlook/Teams/
        Zoom/Slack/WhatsApp connection at all - independence is the
        whole point.
        """
        self._enable_push()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
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
