"""
Integration tests for the Analytics Dashboard Extension's backend
surface: GET /analytics/{overview,reschedule,cancellations,
notifications,integrations,resources,guests,team,insights,export}.

Mirrors tests/test_notification_logs.py's harness: real FastAPI app
via TestClient, in-memory SQLite wired in through a get_db override,
plus the same NotificationLogService.SessionLocal patch (that service
intentionally opens its own independent session - see its docstring -
so it isn't reached by the get_db override and must be patched
separately to land in this test's SQLite DB).

Run with: python -m unittest tests.test_analytics_dashboard -v
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
from app.models.meeting_reschedule_history import (  # noqa: E402
    MeetingRescheduleHistory,
)
from app.models.whatsapp_settings import WhatsAppSettings  # noqa: E402

MEETING_START = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)  # a Monday
MEETING_END = MEETING_START + timedelta(hours=1)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    for attr in (
        "start_time", "end_time", "cancelled_at",
        "previous_start_time", "previous_end_time",
        "new_start_time", "new_end_time",
    ):
        value = getattr(target, attr, None)
        if value is not None and value.tzinfo is None:
            setattr(target, attr, value.replace(tzinfo=timezone.utc))


class AnalyticsDashboardTestCase(unittest.TestCase):

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

        for model in (Meeting, MeetingRescheduleHistory):
            for event_name in ("load", "refresh"):
                event.listen(model, event_name, _reattach_utc_on_load)
                self.addCleanup(
                    event.remove, model, event_name, _reattach_utc_on_load,
                )

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

        # Weekday availability so utilization/focus-time math has a
        # real, non-zero denominator.
        for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"):
            resp = self.client.post(
                "/availability/",
                json={
                    "day_of_week": day,
                    "start_time": "09:00:00",
                    "end_time": "17:00:00",
                    "is_available": True,
                },
                headers=self.auth_headers,
            )
            self.assertEqual(resp.status_code, 201)

    def _create_meeting(self, start, end, title="Sync", resource_id=None):
        payload = {
            "title": title,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        if resource_id is not None:
            payload["resource_id"] = resource_id
        resp = self.client.post("/meetings/", json=payload, headers=self.auth_headers)
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["id"]

    def _range_params(self):
        return {"range": "custom", "start": "2026-08-01", "end": "2026-08-07"}

    def _wide_range_params(self):
        """
        For assertions on action-anchored analytics (cancellation,
        reschedule, notification) - those are anchored on when the
        action happened (real "now" in the test run), not on
        MEETING_START, so a range fixed to August 2026 wouldn't
        contain them.
        """
        return {"range": "custom", "start": "2020-01-01", "end": "2030-01-01"}

    def test_overview_reflects_real_meetings(self):
        self._create_meeting(MEETING_START, MEETING_END)
        self._create_meeting(
            MEETING_START + timedelta(days=1),
            MEETING_END + timedelta(days=1, hours=1),
        )

        resp = self.client.get(
            "/analytics/overview",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()

        total_trend_meetings = sum(
            p["upcoming"] + p["completed"] for p in body["trend_daily"]
        )
        self.assertEqual(total_trend_meetings, 2)
        self.assertGreater(body["duration"]["total_hours"], 0)
        self.assertEqual(body["duration"]["shortest_minutes"], 60)

    def test_overview_with_no_meetings_returns_zeros_not_errors(self):
        resp = self.client.get(
            "/analytics/overview",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["trend_daily"], [])
        self.assertEqual(body["duration"]["average_minutes"], 0)
        self.assertEqual(body["utilization"]["utilization_pct"], 0)

    def test_invalid_range_key_returns_400(self):
        resp = self.client.get(
            "/analytics/overview",
            params={"range": "not-a-real-range"},
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)

    def test_custom_range_without_dates_returns_400(self):
        resp = self.client.get(
            "/analytics/overview",
            params={"range": "custom"},
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 400)

    def test_cancelled_meeting_appears_in_cancellation_analytics(self):
        meeting_id = self._create_meeting(MEETING_START, MEETING_END)
        self.client.delete(f"/meetings/{meeting_id}", headers=self.auth_headers)

        resp = self.client.get(
            "/analytics/cancellations",
            params=self._wide_range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["cancelled_count"], 1)
        # Only the owner can cancel today (see MeetingService
        # .delete_meeting) - this split is 100/0 by construction.
        self.assertEqual(body["cancelled_by_organizer_count"], 1)
        self.assertEqual(body["cancelled_by_participant_count"], 0)

    def test_rescheduled_meeting_appears_in_reschedule_analytics(self):
        meeting_id = self._create_meeting(MEETING_START, MEETING_END)
        update_resp = self.client.put(
            f"/meetings/{meeting_id}",
            json={
                "start_time": (MEETING_START + timedelta(hours=3)).isoformat(),
                "end_time": (MEETING_END + timedelta(hours=3)).isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200)

        resp = self.client.get(
            "/analytics/reschedule",
            params=self._wide_range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["total_rescheduled"], 1)

    def test_notification_analytics_reflects_logged_sends(self):
        db = self.SessionLocal()
        try:
            db.add(
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number="+919876543210",
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
            self._create_meeting(MEETING_START, MEETING_END)

        resp = self.client.get(
            "/analytics/notifications",
            params=self._wide_range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["by_channel"]["whatsapp"]["sent"], 1)
        self.assertEqual(body["overall_success_pct"], 100.0)

    def test_resource_analytics_reflects_bookings(self):
        resource_resp = self.client.post(
            "/resources/",
            json={"name": "Room A", "resource_type": "Room"},
            headers=self.auth_headers,
        )
        self.assertEqual(resource_resp.status_code, 201)
        resource_id = resource_resp.json()["id"]

        self._create_meeting(MEETING_START, MEETING_END, resource_id=resource_id)

        resp = self.client.get(
            "/analytics/resources",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIsNotNone(body["most_used"])
        self.assertEqual(body["most_used"]["booking_count"], 1)
        self.assertEqual(body["physical_meeting_count"], 1)

    def test_guest_analytics_counts_external_guests(self):
        resp = self.client.post(
            "/meetings/",
            json={
                "title": "With guest",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
                "external_guest_emails": ["client@acme.example"],
            },
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201, resp.text)

        analytics_resp = self.client.get(
            "/analytics/guests",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(analytics_resp.status_code, 200, analytics_resp.text)
        body = analytics_resp.json()
        self.assertEqual(body["external_meeting_count"], 1)
        self.assertEqual(body["guest_domains"][0]["domain"], "acme.example")

    def test_integration_analytics_returns_structure(self):
        resp = self.client.get(
            "/analytics/integrations",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertIn("connected_users", body)
        self.assertEqual(body["total_users"], 1)

    def test_team_analytics_with_no_department_set_is_empty_not_error(self):
        resp = self.client.get(
            "/analytics/team",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["by_department"], [])
        self.assertEqual(body["users_with_department_set"], 0)
        self.assertEqual(body["total_users"], 1)

    def test_department_set_via_profile_reflected_in_team_analytics(self):
        update_resp = self.client.put(
            f"/users/{self.owner_id}",
            json={"department": "Engineering"},
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)
        self.assertEqual(update_resp.json()["department"], "Engineering")

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

        self._create_meeting(MEETING_START, MEETING_END)

        resp = self.client.get(
            "/analytics/team",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()
        self.assertEqual(body["total_users"], 2)
        self.assertEqual(body["users_with_department_set"], 1)
        self.assertEqual(body["by_department"], [{"department": "Engineering", "user_count": 1, "meeting_count": 1}])
        # The other user never set a department, so their meetings
        # (there are none here) and identity never surface anywhere in
        # this response - only the aggregate count above.
        self.assertNotIn("Other", str(body))

    def test_insights_empty_when_no_meetings(self):
        resp = self.client.get(
            "/analytics/insights",
            params=self._range_params(),
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["insights"], [])

    def test_export_csv(self):
        self._create_meeting(MEETING_START, MEETING_END)

        resp = self.client.get(
            "/analytics/export",
            params={**self._range_params(), "format": "csv"},
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp.headers["content-type"])
        self.assertIn("Date,Upcoming,Completed", resp.text)

    def test_export_xlsx(self):
        self._create_meeting(MEETING_START, MEETING_END)

        resp = self.client.get(
            "/analytics/export",
            params={**self._range_params(), "format": "xlsx"},
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp.headers["content-type"])
        self.assertGreater(len(resp.content), 0)

    def test_analytics_endpoints_require_auth(self):
        for path in (
            "/analytics/overview", "/analytics/reschedule",
            "/analytics/cancellations", "/analytics/notifications",
            "/analytics/integrations", "/analytics/resources",
            "/analytics/guests", "/analytics/team", "/analytics/insights",
        ):
            resp = self.client.get(path, params=self._range_params())
            self.assertEqual(resp.status_code, 401, path)


if __name__ == "__main__":
    unittest.main()
