"""
Integration tests for Notification Analytics V1: NotificationLogService
.try_record writes a best-effort NotificationLog row from each of the
four channel notification services (email, Slack, WhatsApp, push).

Mirrors tests/test_whatsapp_notifications.py's harness: real FastAPI
app via TestClient, in-memory SQLite wired in through a get_db
override. External sends are mocked at each channel's client boundary
so these tests exercise the real logging wiring without network calls.

Run with: python -m unittest tests.test_notification_logs -v
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
from app.models.notification_log import NotificationLog  # noqa: E402
from app.models.push_subscription import PushSubscription  # noqa: E402
from app.models.slack_credential import SlackCredential  # noqa: E402
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


class NotificationLogsTestCase(unittest.TestCase):

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

        # NotificationLogService.try_record intentionally opens its own
        # independent Session (see its docstring) rather than using the
        # FastAPI-injected, get_db-overridden one - by design, so a
        # logging failure can never touch the caller's transaction.
        # That means it isn't reached by the override_get_db swap
        # above; it must be patched separately so its writes land in
        # this test's in-memory SQLite DB instead of the real
        # configured database.
        session_local_patcher = patch(
            "app.services.notification_log_service.SessionLocal",
            self.SessionLocal,
        )
        session_local_patcher.start()
        self.addCleanup(session_local_patcher.stop)

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
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        )
        self.assertEqual(login_resp.status_code, 200)
        self.auth_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    def _logs(self, channel: str | None = None):
        db = self.SessionLocal()
        try:
            query = db.query(NotificationLog).filter(
                NotificationLog.user_id == self.owner_id,
            )
            if channel:
                query = query.filter(NotificationLog.channel == channel)
            return query.all()
        finally:
            db.close()

    # ---- email (via meeting create's automatic notification hook) ----

    def test_email_notification_logged_on_meeting_create_with_participant(self):
        # Notification recipients come from participants/external
        # guests (see MeetingNotificationService._resolve_recipients) -
        # a meeting with neither has nothing to email, so register a
        # second user and add them as a participant first.
        other_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Participant",
                "email": "participant@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        participant_id = other_resp.json()["id"]

        create_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Sync",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.auth_headers,
        )
        meeting_id = create_resp.json()["id"]

        self.client.post(
            f"/meetings/{meeting_id}/participants",
            json={"user_id": participant_id},
            headers=self.auth_headers,
        )

        # Re-trigger a notification-bearing operation now that a
        # participant exists: update the meeting's title.
        with patch(
            "app.services.email_service.EmailService.try_send_meeting_update",
            return_value=True,
        ):
            update_resp = self.client.put(
                f"/meetings/{meeting_id}",
                json={"title": "Sync (renamed)"},
                headers=self.auth_headers,
            )
        self.assertEqual(update_resp.status_code, 200)

        email_logs = self._logs("email")
        self.assertTrue(any(log.event_type == "updated" and log.success for log in email_logs))

    def test_email_test_endpoint_logs_success_and_failure(self):
        with patch(
            "app.api.email_routes.EmailService.send_email",
            return_value=None,
        ):
            resp = self.client.post("/email/test", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)

        with patch(
            "app.api.email_routes.EmailService.send_email",
            side_effect=Exception("smtp down"),
        ):
            resp = self.client.post("/email/test", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 502)

        logs = self._logs("email")
        test_logs = [log for log in logs if log.event_type == "test"]
        self.assertEqual(len(test_logs), 2)
        self.assertTrue(any(log.success for log in test_logs))
        self.assertTrue(any(not log.success for log in test_logs))

    # ---- whatsapp ----

    def test_whatsapp_notification_logged_on_meeting_create(self):
        db = self.SessionLocal()
        try:
            db.add(
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number=FAKE_PHONE_NUMBER,
                    is_enabled=True,
                )
            )
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=(True, None),
        ):
            resp = self.client.post(
                "/meetings/",
                json={
                    "title": "Standup",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                },
                headers=self.auth_headers,
            )
        self.assertEqual(resp.status_code, 201)

        logs = self._logs("whatsapp")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].event_type, "created")
        self.assertTrue(logs[0].success)
        self.assertIsNone(logs[0].error_detail)

    def test_whatsapp_notification_logs_failure_with_detail(self):
        db = self.SessionLocal()
        try:
            db.add(
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number=FAKE_PHONE_NUMBER,
                    is_enabled=True,
                )
            )
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.whatsapp_notification_service.WhatsAppClient.send_text_message",
            return_value=(False, "Meta API error (131030): not in allowed list"),
        ):
            resp = self.client.post(
                "/meetings/",
                json={
                    "title": "Standup",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                },
                headers=self.auth_headers,
            )
        self.assertEqual(resp.status_code, 201)

        logs = self._logs("whatsapp")
        self.assertEqual(len(logs), 1)
        self.assertFalse(logs[0].success)
        self.assertIn("131030", logs[0].error_detail)

    # ---- push: one log row per subscription ----

    def test_push_notification_logs_one_row_per_subscription(self):
        db = self.SessionLocal()
        try:
            db.add_all([
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint="https://fcm.example/aaa",
                    p256dh_key="key1",
                    auth_key="auth1",
                    is_enabled=True,
                ),
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint="https://fcm.example/bbb",
                    p256dh_key="key2",
                    auth_key="auth2",
                    is_enabled=True,
                ),
            ])
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.push_notification_service.PushClient.send_notification",
            return_value=(True, None),
        ):
            resp = self.client.post(
                "/meetings/",
                json={
                    "title": "Standup",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                },
                headers=self.auth_headers,
            )
        self.assertEqual(resp.status_code, 201)

        logs = self._logs("push")
        self.assertEqual(len(logs), 2)
        self.assertTrue(all(log.success for log in logs))

    # ---- slack: test endpoint ----

    def test_slack_test_notification_logged(self):
        db = self.SessionLocal()
        try:
            db.add(
                SlackCredential(
                    user_id=self.owner_id,
                    access_token="xoxb-fake",
                    team_id="T123",
                    team_name="Fake Team",
                    slack_user_id="U123",
                    scopes="chat:write",
                )
            )
            db.commit()
        finally:
            db.close()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=None,
        ):
            resp = self.client.post("/slack/test", headers=self.auth_headers)
        self.assertEqual(resp.status_code, 200)

        logs = self._logs("slack")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].event_type, "test")
        self.assertTrue(logs[0].success)


if __name__ == "__main__":
    unittest.main()
