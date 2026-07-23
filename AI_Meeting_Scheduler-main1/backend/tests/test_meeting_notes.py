"""
Integration tests for Meeting Notes V1's HTTP surface
(POST/GET/PUT/DELETE /meeting-intelligence/notes/{meeting_id}).

Exercises the real FastAPI app end-to-end through starlette's
TestClient: register -> login -> create meeting -> notes CRUD. The
only substitution is the DB itself (in-memory SQLite instead of the
configured PostgreSQL), wired in via a dependency_overrides on
get_db, mirroring tests/test_auto_reschedule_integration.py.

Run with: python -m unittest tests.test_meeting_notes -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# Registers every mapped model up front so SQLAlchemy can resolve
# string-based relationship() references before create_all runs.
from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


class MeetingNotesIntegrationTestCase(unittest.TestCase):

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

        self.client = TestClient(app)

        self.owner_id, self.owner_headers = self._register_and_login(
            "Owner", "owner@example.com",
        )
        self.participant_id, self.participant_headers = (
            self._register_and_login(
                "Participant", "participant@example.com",
            )
        )
        self.outsider_id, self.outsider_headers = self._register_and_login(
            "Outsider", "outsider@example.com",
        )

        create_resp = self.client.post(
            "/meetings/",
            json={
                "title": "Sync",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.owner_headers,
        )
        self.assertEqual(create_resp.status_code, 201)
        self.meeting_id = create_resp.json()["id"]

        add_participant_resp = self.client.post(
            f"/meetings/{self.meeting_id}/participants",
            json={"user_id": self.participant_id},
            headers=self.owner_headers,
        )
        self.assertEqual(add_participant_resp.status_code, 201)

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

    def _create_note(self, content="Discussed Q3 roadmap."):
        return self.client.post(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": content},
            headers=self.owner_headers,
        )

    # ------------------------------------------------------------
    # Create
    # ------------------------------------------------------------

    def test_owner_can_create_note(self):
        response = self._create_note("  Discussed Q3 roadmap.  ")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["meeting_id"], self.meeting_id)
        # Trimmed of surrounding whitespace.
        self.assertEqual(body["content"], "Discussed Q3 roadmap.")
        self.assertEqual(body["created_by_id"], self.owner_id)

    def test_create_note_escapes_html(self):
        response = self._create_note("<script>alert('xss')</script>")

        self.assertEqual(response.status_code, 201)
        content = response.json()["content"]
        self.assertNotIn("<script>", content)
        self.assertIn("&lt;script&gt;", content)

    def test_create_note_twice_rejected(self):
        first = self._create_note()
        self.assertEqual(first.status_code, 201)

        second = self._create_note("Another note")
        self.assertEqual(second.status_code, 400)

    # ------------------------------------------------------------
    # Read
    # ------------------------------------------------------------

    def test_owner_can_read_note(self):
        self._create_note("Discussed Q3 roadmap.")

        response = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "Discussed Q3 roadmap.")

    def test_participant_can_read_note(self):
        self._create_note("Discussed Q3 roadmap.")

        response = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.participant_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "Discussed Q3 roadmap.")

    def test_non_participant_cannot_read_note(self):
        self._create_note("Discussed Q3 roadmap.")

        response = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.outsider_headers,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------
    # Update
    # ------------------------------------------------------------

    def test_owner_can_update_note(self):
        self._create_note("Original content.")

        response = self.client.put(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "Updated content."},
            headers=self.owner_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "Updated content.")

        get_resp = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.json()["content"], "Updated content.")

    def test_participant_cannot_update_note(self):
        self._create_note("Original content.")

        response = self.client.put(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "Hijacked content."},
            headers=self.participant_headers,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------

    def test_owner_can_delete_note(self):
        self._create_note("To be deleted.")

        delete_resp = self.client.delete(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(delete_resp.status_code, 200)

        get_resp = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.status_code, 404)

    def test_participant_cannot_delete_note(self):
        self._create_note("Should survive.")

        response = self.client.delete(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.participant_headers,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------
    # Unauthorized (not owner, not participant at all)
    # ------------------------------------------------------------

    def test_outsider_cannot_create_note(self):
        response = self.client.post(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "Sneaky note."},
            headers=self.outsider_headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_delete_note(self):
        self._create_note("Should survive.")

        response = self.client.delete(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.outsider_headers,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------
    # Empty note
    # ------------------------------------------------------------

    def test_create_empty_note_rejected(self):
        response = self._create_note("   ")
        self.assertEqual(response.status_code, 422)

    def test_update_empty_note_rejected(self):
        self._create_note("Original content.")

        response = self.client.put(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "   "},
            headers=self.owner_headers,
        )

        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------
    # Meeting not found / note not found
    # ------------------------------------------------------------

    def test_create_note_meeting_not_found(self):
        response = self.client.post(
            "/meeting-intelligence/notes/999999",
            json={"content": "Note for a ghost meeting."},
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_get_note_meeting_not_found(self):
        response = self.client.get(
            "/meeting-intelligence/notes/999999",
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_get_note_not_found(self):
        # Meeting exists but no note has been created yet.
        response = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_update_note_not_found(self):
        response = self.client.put(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "No note exists yet."},
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_delete_note_not_found(self):
        response = self.client.delete(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
