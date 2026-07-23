"""
Regression tests for a real bug found during the production QA pass:
MeetingService.update_meeting never ran conflict detection, so a
manual reschedule (PUT /meetings/{id}) could silently move a meeting
on top of another meeting's slot, or a resource booking on top of
another booking - conflict detection only ever ran on create.

Mirrors tests/test_meeting_reschedule_history.py's harness: real
FastAPI app via TestClient, in-memory SQLite wired in through a
get_db override.

Run with: python -m unittest tests.test_meeting_update_conflict -v
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

DAY1_START = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    for attr in ("start_time", "end_time"):
        value = getattr(target, attr, None)
        if value is not None and value.tzinfo is None:
            setattr(target, attr, value.replace(tzinfo=timezone.utc))


class MeetingUpdateConflictTestCase(unittest.TestCase):

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

        login_resp = self.client.post(
            "/auth/login",
            json={"email": "owner@example.com", "password": "correct horse battery staple"},
        )
        self.assertEqual(login_resp.status_code, 200)
        self.auth_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

    def _create_meeting(self, start, end, **extra):
        resp = self.client.post(
            "/meetings/",
            json={
                "title": "Meeting",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
                **extra,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()

    def test_rescheduling_onto_another_meetings_slot_is_rejected(self):
        meeting_a = self._create_meeting(DAY1_START, DAY1_START + timedelta(hours=1))
        meeting_b_start = DAY1_START + timedelta(hours=2)
        self._create_meeting(meeting_b_start, meeting_b_start + timedelta(hours=1))

        update_resp = self.client.put(
            f"/meetings/{meeting_a['id']}",
            json={
                "start_time": meeting_b_start.isoformat(),
                "end_time": (meeting_b_start + timedelta(hours=1)).isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 400, update_resp.text)
        self.assertIn("conflicts", update_resp.json()["detail"])

    def test_rescheduling_to_a_free_slot_succeeds(self):
        meeting = self._create_meeting(DAY1_START, DAY1_START + timedelta(hours=1))
        new_start = DAY1_START + timedelta(hours=5)

        update_resp = self.client.put(
            f"/meetings/{meeting['id']}",
            json={
                "start_time": new_start.isoformat(),
                "end_time": (new_start + timedelta(hours=1)).isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)
        returned_start = update_resp.json()["start_time"].replace("Z", "+00:00")
        self.assertEqual(datetime.fromisoformat(returned_start), new_start)

    def test_shifting_a_meeting_that_overlaps_its_own_old_slot_does_not_self_conflict(self):
        """A reschedule that shifts by less than its own duration means
        the old and new ranges overlap - update_meeting must exclude
        the meeting's own (pre-mutation) row from the conflict check,
        or every small reschedule would be rejected as "conflicting"
        with itself."""
        meeting = self._create_meeting(DAY1_START, DAY1_START + timedelta(hours=2))
        shifted_start = DAY1_START + timedelta(minutes=30)

        update_resp = self.client.put(
            f"/meetings/{meeting['id']}",
            json={
                "start_time": shifted_start.isoformat(),
                "end_time": (shifted_start + timedelta(hours=2)).isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)

    def test_renaming_a_meeting_with_an_existing_resource_does_not_self_conflict(self):
        resource_resp = self.client.post(
            "/resources/",
            json={"name": "Room A", "resource_type": "room"},
            headers=self.auth_headers,
        )
        self.assertEqual(resource_resp.status_code, 201, resource_resp.text)
        resource_id = resource_resp.json()["id"]

        meeting = self._create_meeting(
            DAY1_START, DAY1_START + timedelta(hours=1), resource_id=resource_id,
        )

        update_resp = self.client.put(
            f"/meetings/{meeting['id']}",
            json={"title": "Renamed"},
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 200, update_resp.text)

    def test_rebooking_a_resource_onto_another_meetings_booking_is_rejected(self):
        resource_resp = self.client.post(
            "/resources/",
            json={"name": "Room A", "resource_type": "room"},
            headers=self.auth_headers,
        )
        self.assertEqual(resource_resp.status_code, 201, resource_resp.text)
        resource_id = resource_resp.json()["id"]

        meeting_a = self._create_meeting(DAY1_START, DAY1_START + timedelta(hours=1))

        # A second, distinct owner books the resource at a different
        # time - this isolates the resource-conflict check from the
        # owner-conflict check (both meetings would also trip the
        # owner check if they shared an owner).
        self.client.post(
            "/auth/register",
            json={
                "name": "Other Owner",
                "email": "other-owner@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        other_login = self.client.post(
            "/auth/login",
            json={"email": "other-owner@example.com", "password": "correct horse battery staple"},
        )
        other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

        booked_start = DAY1_START + timedelta(hours=3)
        booked_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Other meeting",
                "start_time": booked_start.isoformat(),
                "end_time": (booked_start + timedelta(hours=1)).isoformat(),
                "resource_id": resource_id,
            },
            headers=other_headers,
        )
        self.assertEqual(booked_resp.status_code, 201, booked_resp.text)

        update_resp = self.client.put(
            f"/meetings/{meeting_a['id']}",
            json={
                "start_time": booked_start.isoformat(),
                "end_time": (booked_start + timedelta(hours=1)).isoformat(),
                "resource_id": resource_id,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(update_resp.status_code, 400, update_resp.text)
        self.assertIn("already booked", update_resp.json()["detail"])


if __name__ == "__main__":
    unittest.main()
