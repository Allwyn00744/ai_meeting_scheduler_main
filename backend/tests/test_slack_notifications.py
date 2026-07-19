"""
Integration tests for Slack Notifications V1: the automatic best-effort
hooks in MeetingService.create_meeting/update_meeting/delete_meeting and
SchedulerService.schedule_meeting/update_meeting, plus the manual POST
/slack/send/{meeting_id} endpoint. Mirrors the style of
tests/test_zoom_meeting_integration.py: a real FastAPI app via
starlette's TestClient, backed by an in-memory SQLite DB.

Slack API calls are mocked at the SlackAPI boundary (post_message) so
these tests exercise the real service/repository/route wiring without
making network calls. The "Slack not connected" paths are exercised
for real, with no mocking at all - mirrors how the existing Zoom
integration tests rely on a real no-op rather than a patched-out one.

Run with: python -m unittest tests.test_slack_notifications -v
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
from app.models.slack_credential import SlackCredential  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

FAKE_SLACK_RESPONSE = {"ok": True, "channel": "U123", "ts": "1234567890.123456"}


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class SlackNotificationsTestCase(unittest.TestCase):

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

    def _connect_slack(self, user_id: int | None = None):
        """Directly persists a SlackCredential row, bypassing the OAuth
        flow itself - that flow is covered by test_slack_oauth.py."""
        db = self.SessionLocal()
        try:
            db.add(
                SlackCredential(
                    user_id=user_id or self.owner_id,
                    access_token="xoxb-fake-bot-token",
                    team_id="T123",
                    team_name="Fake Team",
                    slack_user_id="U123",
                    scopes="chat:write",
                )
            )
            db.commit()
        finally:
            db.close()

    def _set_full_availability(self, headers=None):
        """
        AvailabilityService.is_user_available() requires an explicit
        Availability row for a day before it treats the owner as
        available on it - required by SchedulerService.schedule_meeting,
        see tests/test_auto_reschedule_integration.py for the same
        setup.
        """
        for day in (
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ):
            resp = self.client.post(
                "/availability/",
                json={
                    "day_of_week": day,
                    "start_time": "00:00:00",
                    "end_time": "23:59:59",
                    "is_available": True,
                },
                headers=headers or self.auth_headers,
            )
            self.assertEqual(resp.status_code, 201)

    def _create_meeting_slack_muted(self, headers=None):
        """
        Creates a meeting with Slack already connected, muting the
        automatic create-time Slack call (mocked to succeed but not
        asserted on) so tests focused on a *different* operation don't
        make a real network call as a side effect of setup.
        """
        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ):
            return self._create_meeting(headers=headers)

    # ---- automatic hook: MeetingService.create_meeting ----

    def test_create_meeting_skips_gracefully_when_slack_not_connected(self):
        # No SlackAPI mock at all - if the hook tried a real network
        # call here without a credential short-circuit, this would hang
        # or fail instead of the create succeeding cleanly.
        meeting_id = self._create_meeting()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)

    def test_create_meeting_notifies_slack_when_connected(self):
        self._connect_slack()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            self._create_meeting()

        mock_post.assert_called_once()
        self.assertIn("Meeting Created", mock_post.call_args.kwargs["text"])

    def test_create_meeting_slack_outage_does_not_block_creation(self):
        self._connect_slack()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
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

    # ---- automatic hook: MeetingService.update_meeting ----

    def test_update_meeting_notifies_slack_when_connected(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            resp = self.client.put(
                f"/meetings/{meeting_id}",
                json={"title": "Standup (moved)"},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_post.assert_called_once()
        self.assertIn("Meeting Updated", mock_post.call_args.kwargs["text"])

    # ---- automatic hook: MeetingService.delete_meeting ----

    def test_delete_meeting_notifies_slack_when_connected(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_post.assert_called_once()
        self.assertIn("Meeting Cancelled", mock_post.call_args.kwargs["text"])
        # Cancellation messages omit location - see
        # SlackNotificationService._build_message.
        self.assertNotIn("Location", mock_post.call_args.kwargs["text"])

    def test_delete_meeting_slack_outage_does_not_block_deletion(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            side_effect=Exception("boom"),
        ):
            resp = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)

    # ---- automatic hooks: SchedulerService.schedule_meeting / update_meeting ----

    def test_scheduler_schedule_meeting_notifies_slack(self):
        self._connect_slack()
        self._set_full_availability()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            resp = self.client.post(
                "/scheduler/schedule",
                json={
                    "title": "Planning",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                    "participant_ids": [],
                },
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 201)
        mock_post.assert_called_once()
        self.assertIn("Meeting Created", mock_post.call_args.kwargs["text"])

    def test_scheduler_update_meeting_notifies_slack(self):
        """
        SchedulerService.update_meeting has its own Slack hook (added
        as a sibling to its own MeetingNotificationService.
        notify_meeting_updated call), mirroring the same pattern used
        for MeetingService.update_meeting. Exercised directly against
        the service, since - like SchedulerService.update_meeting
        itself - this method is not wired to any route today (a
        pre-existing gap, unrelated to Slack); MeetingService.
        update_meeting is what handles PUT /meetings/{id}.
        """
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        db = self.SessionLocal()
        try:
            from app.models.user import User
            from app.schemas.meeting import MeetingUpdate
            from app.services.scheduler_service import SchedulerService

            current_user = db.query(User).filter(
                User.id == self.owner_id
            ).first()

            with patch(
                "app.services.slack_notification_service.SlackAPI.post_message",
                return_value=FAKE_SLACK_RESPONSE,
            ) as mock_post:
                SchedulerService.update_meeting(
                    db,
                    meeting_id,
                    MeetingUpdate(title="Planning (moved)"),
                    current_user,
                )
        finally:
            db.close()

        mock_post.assert_called_once()
        self.assertIn("Meeting Updated", mock_post.call_args.kwargs["text"])

    # ---- manual send: POST /slack/send/{meeting_id} ----

    def test_manual_send_requires_slack_connected(self):
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/slack/send/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_send_success(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            response = self.client.post(
                f"/slack/send/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sent successfully", response.json()["message"])
        mock_post.assert_called_once()

    def test_manual_send_meeting_not_found(self):
        self._connect_slack()

        response = self.client.post(
            "/slack/send/999999",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_send_unauthorized_wrong_owner(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        response = self.client.post(
            f"/slack/send/{meeting_id}",
            headers=self.other_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_manual_send_no_token_unauthorized(self):
        meeting_id = self._create_meeting()
        response = self.client.post(f"/slack/send/{meeting_id}")
        self.assertEqual(response.status_code, 401)

    def test_manual_send_slack_failure_returns_502(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            side_effect=Exception("boom"),
        ):
            response = self.client.post(
                f"/slack/send/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 502)

    def test_manual_send_content_matches_automatic_notification_shape(self):
        self._connect_slack()
        meeting_id = self._create_meeting_slack_muted()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            self.client.post(
                f"/slack/send/{meeting_id}",
                headers=self.auth_headers,
            )

        text = mock_post.call_args.kwargs["text"]
        self.assertIn("Standup", text)
        self.assertIn("Start:", text)
        self.assertIn("End:", text)
        self.assertIn("Location:", text)

    # ---- independence from other providers ----

    def test_slack_notification_does_not_require_other_providers(self):
        """
        Slack Notifications V1 must work with no Google/Outlook/Teams/
        Zoom connection at all - independence is the whole point.
        """
        self._connect_slack()

        with patch(
            "app.services.slack_notification_service.SlackAPI.post_message",
            return_value=FAKE_SLACK_RESPONSE,
        ) as mock_post:
            meeting_id = self._create_meeting()

        mock_post.assert_called_once()

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
