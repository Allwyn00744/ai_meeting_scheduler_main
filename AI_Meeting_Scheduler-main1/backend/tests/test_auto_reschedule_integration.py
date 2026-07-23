"""
Integration test for Auto Rescheduling V1's HTTP surface.

Unlike tests/test_auto_reschedule.py (service-layer unit tests against
mocked repositories), this exercises the real FastAPI app end-to-end
through starlette's TestClient: register -> login -> create meeting ->
POST /scheduler/meetings/{id}/auto-reschedule -> verify both the HTTP
response and the row actually persisted in the database. The only
substitution is the DB itself (in-memory SQLite instead of the
configured PostgreSQL), wired in via a dependency_overrides on get_db -
every model here uses plain, portable SQLAlchemy column types, so the
schema is identical in shape. Google Calendar and SMTP are not mocked:
the test owner has no stored Google credential (so calendar sync
short-circuits on its own "not connected" branch) and the meeting has
no participants/external guests (so no recipient exists to email to) -
both are exercised as real no-ops rather than patched out.

Run with: python -m unittest tests.test_auto_reschedule_integration -v
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

# Registers every mapped model up front so SQLAlchemy can resolve
# string-based relationship() references before create_all runs.
from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


def _reattach_utc_on_load(target, *_args):
    """
    SQLite (unlike the app's real PostgreSQL) drops tzinfo on
    DateTime(timezone=True) columns: values round-trip back as naive
    datetimes. Meeting.start_time/end_time being naive would make
    AvailabilityService.is_user_available() reject every candidate
    slot outright (it requires tzinfo), which is a SQLite storage
    quirk, not app behavior under its real PostgreSQL database. This
    listener compensates for that gap in the in-memory test DB only.
    Registered for both "load" (first SELECT) and "refresh" (the
    db.refresh() every repository write does) since SQLAlchemy fires
    a different event for each.
    """
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class AutoRescheduleIntegrationTestCase(unittest.TestCase):

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

        # The user registered above has UTC as their timezone, and
        # AvailabilityService.is_user_available() requires an explicit
        # Availability row for a day before it will treat the owner as
        # available on it - a freshly registered user has none, so the
        # slot search would find nothing without this. Cover every day
        # of the week so the search window (which can cross a day
        # boundary) never runs into a gap.
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

    def test_auto_reschedule_success_via_http(self):
        response = self.client.post(
            f"/scheduler/meetings/{self.meeting_id}/auto-reschedule",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()

        # Response matches the AutoRescheduleResponse contract.
        self.assertEqual(
            set(body.keys()),
            {
                "meeting",
                "previous_start_time",
                "previous_end_time",
                "new_start_time",
                "new_end_time",
                "message",
            },
        )
        self.assertEqual(body["meeting"]["id"], self.meeting_id)

        previous_start = datetime.fromisoformat(body["previous_start_time"])
        new_start = datetime.fromisoformat(body["new_start_time"])
        new_end = datetime.fromisoformat(body["new_end_time"])

        self.assertEqual(previous_start, MEETING_START)
        # Meeting time changed.
        self.assertNotEqual(new_start, MEETING_START)
        # Duration preserved.
        self.assertEqual(new_end - new_start, MEETING_END - MEETING_START)

        meeting_body = body["meeting"]
        self.assertEqual(
            datetime.fromisoformat(meeting_body["start_time"]), new_start,
        )
        self.assertEqual(
            datetime.fromisoformat(meeting_body["end_time"]), new_end,
        )

        # Database updated: fetch through a fresh session/connection,
        # independent of whatever session the request handler used.
        get_resp = self.client.get(
            f"/meetings/{self.meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        persisted = get_resp.json()
        self.assertEqual(
            datetime.fromisoformat(persisted["start_time"]), new_start,
        )
        self.assertEqual(
            datetime.fromisoformat(persisted["end_time"]), new_end,
        )

        # No duplicate row was created by the reschedule.
        list_resp = self.client.get("/meetings/", headers=self.auth_headers)
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(len(list_resp.json()), 1)


if __name__ == "__main__":
    unittest.main()
