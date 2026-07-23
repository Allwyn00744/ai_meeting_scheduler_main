"""
Integration tests for Reschedule Analytics V1: MeetingService
.update_meeting now writes a MeetingRescheduleHistory row whenever
start_time/end_time actually change, covering both a manual PUT
/meetings/{id} and SchedulerService.auto_reschedule_meeting (which
persists through the same update_meeting call).

Mirrors tests/test_meeting_action_items.py's harness: real FastAPI app
via TestClient, in-memory SQLite wired in through a get_db override.

Run with: python -m unittest tests.test_meeting_reschedule_history -v
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
from app.models.meeting_reschedule_history import (  # noqa: E402
    MeetingRescheduleHistory,
)

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)
NEW_START = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)
NEW_END = NEW_START + timedelta(hours=1)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    for attr in (
        "start_time", "end_time",
        "previous_start_time", "previous_end_time",
        "new_start_time", "new_end_time",
    ):
        value = getattr(target, attr, None)
        if value is not None and value.tzinfo is None:
            setattr(target, attr, value.replace(tzinfo=timezone.utc))


class MeetingRescheduleHistoryTestCase(unittest.TestCase):

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

        create_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Sync",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(create_resp.status_code, 201)
        self.meeting_id = create_resp.json()["id"]

    def _history_rows(self):
        db = self.SessionLocal()
        try:
            return (
                db.query(MeetingRescheduleHistory)
                .filter(MeetingRescheduleHistory.meeting_id == self.meeting_id)
                .all()
            )
        finally:
            db.close()

    def test_changing_start_and_end_time_records_history(self):
        update_resp = self.client.put(
            f"/meetings/{self.meeting_id}",
            json={
                "start_time": NEW_START.isoformat(),
                "end_time": NEW_END.isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)

        rows = self._history_rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.previous_start_time, MEETING_START)
        self.assertEqual(row.previous_end_time, MEETING_END)
        self.assertEqual(row.new_start_time, NEW_START)
        self.assertEqual(row.new_end_time, NEW_END)
        self.assertEqual(row.rescheduled_by_id, self.owner_id)

    def test_changing_only_title_does_not_record_history(self):
        update_resp = self.client.put(
            f"/meetings/{self.meeting_id}",
            json={"title": "Renamed"},
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(self._history_rows(), [])

    def test_setting_start_time_to_the_same_value_does_not_record_history(self):
        update_resp = self.client.put(
            f"/meetings/{self.meeting_id}",
            json={
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200)
        self.assertEqual(self._history_rows(), [])

    def test_auto_reschedule_records_history(self):
        for day in (
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ):
            availability_resp = self.client.post(
                "/availability/",
                json={
                    "day_of_week": day,
                    "start_time": "00:00:00",
                    "end_time": "23:59:59",
                    "is_available": True,
                },
                headers=self.auth_headers,
            )
            self.assertEqual(availability_resp.status_code, 201)

        auto_resp = self.client.post(
            f"/scheduler/meetings/{self.meeting_id}/auto-reschedule",
            headers=self.auth_headers,
        )
        self.assertEqual(auto_resp.status_code, 200, auto_resp.text)

        rows = self._history_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].previous_start_time, MEETING_START)


if __name__ == "__main__":
    unittest.main()
