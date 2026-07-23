"""
Integration tests for Cancellation Analytics V1's core behavior
change: MeetingService.delete_meeting now soft-deletes (status
"cancelled" + cancelled_at/cancelled_by_id set) instead of removing
the row, so cancelled meetings survive as an audit trail.

This is the highest-risk change in the Analytics Dashboard Extension:
every read path in MeetingRepository that used to get "free" exclusion
of a cancelled meeting via hard delete now needs an explicit
`status != "cancelled"` filter. These tests focus specifically on the
correctness-critical paths - conflict/resource-booking detection must
still treat a cancelled slot as free, and normal listings must still
exclude cancelled meetings by default - plus the new guard rails
(can't double-cancel, can't edit a cancelled meeting, can't set
status="cancelled" via PUT).

Mirrors tests/test_meeting_action_items.py's harness: real FastAPI app
via TestClient, in-memory SQLite wired in through a get_db override.

Run with: python -m unittest tests.test_meeting_cancellation_soft_delete -v
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

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class MeetingCancellationSoftDeleteTestCase(unittest.TestCase):

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

        self.owner_id, self.owner_headers = self._register_and_login(
            "Owner", "owner@example.com",
        )

    def _register_and_login(self, name: str, email: str):
        register_resp = self.client.post(
            "/auth/register",
            json={
                "name": name,
                "email": email,
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(register_resp.status_code, 201)
        user_id = register_resp.json()["id"]

        login_resp = self.client.post(
            "/auth/login",
            json={"email": email, "password": "correct horse battery staple"},
        )
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.json()["access_token"]

        return user_id, {"Authorization": f"Bearer {token}"}

    def _create_meeting(self, title="Sync", start=MEETING_START, end=MEETING_END, resource_id=None):
        payload = {
            "title": title,
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
        }
        if resource_id is not None:
            payload["resource_id"] = resource_id

        resp = self.client.post(
            "/meetings/",
            json=payload,
            headers=self.owner_headers,
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["id"]

    def test_cancel_meeting_soft_deletes_and_is_still_readable_by_id(self):
        meeting_id = self._create_meeting()

        delete_resp = self.client.delete(
            f"/meetings/{meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(delete_resp.status_code, 200)

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["status"], "cancelled")

    def test_cancelled_meeting_excluded_from_default_list(self):
        meeting_id = self._create_meeting()
        self.client.delete(f"/meetings/{meeting_id}", headers=self.owner_headers)

        list_resp = self.client.get("/meetings/", headers=self.owner_headers)
        self.assertEqual(list_resp.status_code, 200)
        ids = [m["id"] for m in list_resp.json()]
        self.assertNotIn(meeting_id, ids)

    def test_cancelled_meeting_still_returned_by_explicit_status_filter(self):
        meeting_id = self._create_meeting()
        self.client.delete(f"/meetings/{meeting_id}", headers=self.owner_headers)

        filter_resp = self.client.get(
            "/meetings/filter/status",
            params={"status": "cancelled"},
            headers=self.owner_headers,
        )
        self.assertEqual(filter_resp.status_code, 200)
        ids = [m["id"] for m in filter_resp.json()]
        self.assertIn(meeting_id, ids)

    def test_cancelled_meeting_frees_owner_slot_for_a_new_booking(self):
        first_id = self._create_meeting(title="First")
        self.client.delete(f"/meetings/{first_id}", headers=self.owner_headers)

        # Same owner, exact same time range that would have conflicted
        # with the now-cancelled meeting.
        second_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Second",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.owner_headers,
        )
        self.assertEqual(second_resp.status_code, 201, second_resp.text)

    def test_active_meeting_still_blocks_a_conflicting_booking(self):
        # Control case: an active (non-cancelled) meeting must still
        # block, proving the exclusion filter is specific to
        # status == "cancelled" and not a blanket regression.
        self._create_meeting(title="First")

        second_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Second",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.owner_headers,
        )
        self.assertEqual(second_resp.status_code, 400)

    def test_cancelled_meeting_frees_resource_slot(self):
        resource_resp = self.client.post(
            "/resources/",
            json={"name": "Room A", "resource_type": "Room"},
            headers=self.owner_headers,
        )
        self.assertEqual(resource_resp.status_code, 201, resource_resp.text)
        resource_id = resource_resp.json()["id"]

        first_id = self._create_meeting(
            title="First",
            start=MEETING_START,
            end=MEETING_END,
            resource_id=resource_id,
        )
        self.client.delete(f"/meetings/{first_id}", headers=self.owner_headers)

        second_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Second",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
                "resource_id": resource_id,
            },
            headers=self.owner_headers,
        )
        self.assertEqual(second_resp.status_code, 201, second_resp.text)

    def test_cancelling_an_already_cancelled_meeting_returns_404(self):
        meeting_id = self._create_meeting()
        self.client.delete(f"/meetings/{meeting_id}", headers=self.owner_headers)

        second_delete_resp = self.client.delete(
            f"/meetings/{meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(second_delete_resp.status_code, 404)

    def test_updating_a_cancelled_meeting_returns_404(self):
        meeting_id = self._create_meeting()
        self.client.delete(f"/meetings/{meeting_id}", headers=self.owner_headers)

        update_resp = self.client.put(
            f"/meetings/{meeting_id}",
            json={"title": "Resurrected"},
            headers=self.owner_headers,
        )
        self.assertEqual(update_resp.status_code, 404)

    def test_setting_status_cancelled_via_put_is_rejected(self):
        meeting_id = self._create_meeting()

        update_resp = self.client.put(
            f"/meetings/{meeting_id}",
            json={"status": "cancelled"},
            headers=self.owner_headers,
        )
        self.assertEqual(update_resp.status_code, 400)

        # The meeting must remain active - the rejected PUT must not
        # have partially applied.
        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.json()["status"], "scheduled")


if __name__ == "__main__":
    unittest.main()
