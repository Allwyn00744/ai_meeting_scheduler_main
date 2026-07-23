"""
Tests for app/jobs/scheduler.py's mark_completed_meetings - the
background job that fixes a real, previously-latent gap: nothing
anywhere transitioned Meeting.status to "completed" before this
session, so it stayed "scheduled" forever regardless of whether the
meeting had actually happened.

Calls mark_completed_meetings() directly rather than exercising the
AsyncIOScheduler wiring itself (which is disabled under `python -m
unittest` by design - see the module docstring in scheduler.py).

Run with: python -m unittest tests.test_background_jobs -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.jobs.scheduler import mark_completed_meetings  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402
from app.models.user import User  # noqa: E402

NOW = datetime.now(timezone.utc)


class BackgroundJobsTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        # mark_completed_meetings opens its own independent session
        # via SessionLocal - patch that reference to this test's
        # in-memory engine, mirroring how tests/test_notification_logs.py
        # patches NotificationLogService's SessionLocal.
        patcher = patch("app.jobs.scheduler.SessionLocal", self.SessionLocal)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.engine.dispose)

        db = self.SessionLocal()
        try:
            user = User(
                name="Owner",
                email="owner@example.com",
                hashed_password="x",
                timezone="UTC",
            )
            db.add(user)
            db.commit()
            self.owner_id = user.id
        finally:
            db.close()

    def _add_meeting(self, status, start, end):
        db = self.SessionLocal()
        try:
            meeting = Meeting(
                title="Test",
                start_time=start,
                end_time=end,
                owner_id=self.owner_id,
                status=status,
            )
            db.add(meeting)
            db.commit()
            db.refresh(meeting)
            return meeting.id
        finally:
            db.close()

    def _status_of(self, meeting_id):
        db = self.SessionLocal()
        try:
            return db.query(Meeting).filter(Meeting.id == meeting_id).first().status
        finally:
            db.close()

    def test_marks_past_scheduled_meeting_as_completed(self):
        meeting_id = self._add_meeting(
            "scheduled", NOW - timedelta(hours=2), NOW - timedelta(hours=1),
        )

        updated_count = mark_completed_meetings()

        self.assertEqual(updated_count, 1)
        self.assertEqual(self._status_of(meeting_id), "completed")

    def test_does_not_touch_future_meeting(self):
        meeting_id = self._add_meeting(
            "scheduled", NOW + timedelta(hours=1), NOW + timedelta(hours=2),
        )

        mark_completed_meetings()

        self.assertEqual(self._status_of(meeting_id), "scheduled")

    def test_does_not_touch_cancelled_meeting(self):
        meeting_id = self._add_meeting(
            "cancelled", NOW - timedelta(hours=2), NOW - timedelta(hours=1),
        )

        mark_completed_meetings()

        self.assertEqual(self._status_of(meeting_id), "cancelled")

    def test_does_not_touch_already_completed_meeting(self):
        meeting_id = self._add_meeting(
            "completed", NOW - timedelta(hours=2), NOW - timedelta(hours=1),
        )

        updated_count = mark_completed_meetings()

        self.assertEqual(updated_count, 0)
        self.assertEqual(self._status_of(meeting_id), "completed")

    def test_ongoing_meeting_not_yet_ended_is_untouched(self):
        meeting_id = self._add_meeting(
            "scheduled", NOW - timedelta(minutes=30), NOW + timedelta(minutes=30),
        )

        mark_completed_meetings()

        self.assertEqual(self._status_of(meeting_id), "scheduled")


if __name__ == "__main__":
    unittest.main()
