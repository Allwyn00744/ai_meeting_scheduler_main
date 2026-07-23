"""
Integration tests for Recurring Meetings V1 (POST /meeting-series/,
GET /meeting-series/{id}, PUT/DELETE /meeting-series/{id}/from/{seq}) -
a true series engine, distinct from and not touching the existing
weekly-only bulk-create in scheduler_service.py
(ScheduleMeetingRequest.repeat/repeat_type/occurrences).

Mirrors tests/test_meeting_action_items.py's harness: real FastAPI app
via TestClient, in-memory SQLite wired in through a get_db override.

Run with: python -m unittest tests.test_meeting_series -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402

SERIES_START = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)  # a Monday
SERIES_END = SERIES_START + timedelta(hours=1)


def _parse(iso_string: str) -> datetime:
    """Python 3.10's datetime.fromisoformat doesn't accept a trailing 'Z' (fixed in 3.11) - see test_auto_reschedule_integration.py."""
    return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class MeetingSeriesTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

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

        login_resp = self.client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        )
        self.auth_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    def _create_series(self, **overrides):
        payload = {
            "title": "Weekly Standup",
            "start_time": SERIES_START.isoformat(),
            "end_time": SERIES_END.isoformat(),
            "cadence": "weekly",
            "interval": 1,
            "occurrence_count": 4,
        }
        payload.update(overrides)
        return self.client.post(
            "/meeting-series/", json=payload, headers=self.auth_headers,
        )

    def test_create_weekly_series_creates_n_meetings_seven_days_apart(self):
        resp = self._create_series()
        self.assertEqual(resp.status_code, 201, resp.text)
        body = resp.json()

        self.assertEqual(body["occurrence_count"], 4)
        self.assertEqual(len(body["meetings"]), 4)

        starts = [_parse(m["start_time"]) for m in body["meetings"]]
        for i in range(1, len(starts)):
            self.assertEqual((starts[i] - starts[i - 1]).days, 7)

        sequences = [m["series_sequence"] for m in body["meetings"]]
        self.assertEqual(sequences, [0, 1, 2, 3])

    def test_create_daily_series(self):
        resp = self._create_series(cadence="daily", interval=2, occurrence_count=3)
        self.assertEqual(resp.status_code, 201, resp.text)
        starts = [_parse(m["start_time"]) for m in resp.json()["meetings"]]
        for i in range(1, len(starts)):
            self.assertEqual((starts[i] - starts[i - 1]).days, 2)

    def test_create_monthly_series_clamps_day_of_month(self):
        jan_31 = datetime(2026, 1, 31, 10, 0, tzinfo=timezone.utc)
        resp = self._create_series(
            cadence="monthly",
            occurrence_count=2,
            start_time=jan_31.isoformat(),
            end_time=(jan_31 + timedelta(hours=1)).isoformat(),
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        starts = [_parse(m["start_time"]) for m in resp.json()["meetings"]]
        self.assertEqual(starts[0].day, 31)
        # Feb has no 31st - must clamp, not raise or skip to March.
        self.assertEqual(starts[1].month, 2)
        self.assertEqual(starts[1].day, 28)

    def test_series_conflict_rolls_back_all_created_occurrences(self):
        # A pre-existing meeting that only the 3rd occurrence collides with.
        colliding_start = SERIES_START + timedelta(weeks=2)
        pre_existing = self.client.post(
            "/meetings/",
            json={
                "title": "Blocker",
                "start_time": colliding_start.isoformat(),
                "end_time": (colliding_start + timedelta(hours=1)).isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(pre_existing.status_code, 201)

        resp = self._create_series(occurrence_count=4)
        self.assertEqual(resp.status_code, 400, resp.text)

        # The first two occurrences that succeeded before the conflict
        # must have been rolled back, not left as an orphaned partial
        # series.
        list_resp = self.client.get("/meetings/", headers=self.auth_headers)
        titles = [m["title"] for m in list_resp.json()]
        self.assertNotIn("Weekly Standup", titles)

    def test_get_series_requires_ownership(self):
        create_resp = self._create_series()
        series_id = create_resp.json()["id"]

        other_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        other_login = self.client.post(
            "/auth/login",
            json={"email": "other@example.com", "password": "correct horse battery staple"},
        )
        other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

        forbidden_resp = self.client.get(
            f"/meeting-series/{series_id}", headers=other_headers,
        )
        self.assertEqual(forbidden_resp.status_code, 403)

    def test_update_this_and_following_shifts_time_and_keeps_earlier_occurrences(self):
        create_resp = self._create_series()
        series_id = create_resp.json()["id"]

        update_resp = self.client.put(
            f"/meeting-series/{series_id}/from/2",
            json={"time_shift_minutes": 60},
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)
        updated_meetings = update_resp.json()
        self.assertEqual(len(updated_meetings), 2)

        series_resp = self.client.get(
            f"/meeting-series/{series_id}", headers=self.auth_headers,
        )
        meetings = sorted(series_resp.json()["meetings"], key=lambda m: m["series_sequence"])

        original_hour = SERIES_START.hour
        self.assertEqual(
            _parse(meetings[0]["start_time"]).hour, original_hour,
        )
        self.assertEqual(
            _parse(meetings[1]["start_time"]).hour, original_hour,
        )
        self.assertEqual(
            _parse(meetings[2]["start_time"]).hour, original_hour + 1,
        )
        self.assertEqual(
            _parse(meetings[3]["start_time"]).hour, original_hour + 1,
        )

    def test_update_this_and_following_changes_title(self):
        create_resp = self._create_series()
        series_id = create_resp.json()["id"]

        update_resp = self.client.put(
            f"/meeting-series/{series_id}/from/1",
            json={"title": "Renamed Standup"},
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)

        series_resp = self.client.get(
            f"/meeting-series/{series_id}", headers=self.auth_headers,
        )
        meetings = sorted(series_resp.json()["meetings"], key=lambda m: m["series_sequence"])
        self.assertEqual(meetings[0]["title"], "Weekly Standup")
        self.assertEqual(meetings[1]["title"], "Renamed Standup")
        self.assertEqual(meetings[3]["title"], "Renamed Standup")

    def test_cancel_this_and_following_soft_deletes_only_selected_occurrences(self):
        create_resp = self._create_series()
        series_id = create_resp.json()["id"]

        cancel_resp = self.client.delete(
            f"/meeting-series/{series_id}/from/2", headers=self.auth_headers,
        )
        self.assertEqual(cancel_resp.status_code, 200, cancel_resp.text)
        self.assertEqual(cancel_resp.json()["cancelled_count"], 2)

        list_resp = self.client.get("/meetings/", headers=self.auth_headers)
        remaining_titles = [m["title"] for m in list_resp.json()]
        self.assertEqual(remaining_titles.count("Weekly Standup"), 2)

    def test_cancelling_a_single_occurrence_via_normal_delete_still_works(self):
        # Cancelling one occurrence needs no series-aware code at all -
        # the plain DELETE /meetings/{id} already handles it.
        create_resp = self._create_series()
        meeting_id = create_resp.json()["meetings"][1]["id"]

        delete_resp = self.client.delete(
            f"/meetings/{meeting_id}", headers=self.auth_headers,
        )
        self.assertEqual(delete_resp.status_code, 200)

        list_resp = self.client.get("/meetings/", headers=self.auth_headers)
        remaining_titles = [m["title"] for m in list_resp.json()]
        self.assertEqual(remaining_titles.count("Weekly Standup"), 3)

    def test_meeting_series_routes_require_auth(self):
        resp = self.client.post("/meeting-series/", json={})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
