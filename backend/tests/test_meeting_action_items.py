"""
Integration tests for Meeting Intelligence V3's HTTP surface
(POST/GET /meeting-intelligence/action-items/{meeting_id}, PUT/DELETE
/meeting-intelligence/action-items/{action_item_id}).

Mirrors tests/test_meeting_summary.py's harness: real FastAPI app via
TestClient, in-memory SQLite wired in through a get_db override.
GeminiService.generate_json is mocked via unittest.mock.patch.object,
mirroring tests/test_ai_voice_recipient_resolution.py.

Run with: python -m unittest tests.test_meeting_action_items -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException, status  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

# Registers every mapped model up front so SQLAlchemy can resolve
# string-based relationship() references before create_all runs.
from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting_note import MeetingNote  # noqa: E402
from app.models.meeting_owner_action_item import (  # noqa: E402
    MeetingOwnerActionItem,
)
from app.models.meeting_action_item import MeetingActionItem  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

SAMPLE_GEMINI_OUTPUT = {
    "action_items": [
        {
            "task": "Prepare Docker deployment",
            "assignee": "John",
            "due_date": "2026-08-01",
            "priority": "High",
        },
        {
            "task": "Draft rollout plan",
            "assignee": None,
            "due_date": None,
            "priority": "Low",
        },
    ]
}


class MeetingActionItemIntegrationTestCase(unittest.TestCase):

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

    def _generate(self, headers=None, meeting_id=None):
        return self.client.post(
            f"/meeting-intelligence/action-items/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    def _list(self, headers=None, meeting_id=None):
        return self.client.get(
            f"/meeting-intelligence/action-items/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    def _update_status(self, action_item_id, new_status, headers=None):
        return self.client.put(
            f"/meeting-intelligence/action-items/{action_item_id}",
            json={"status": new_status},
            headers=headers or self.owner_headers,
        )

    def _delete(self, action_item_id, headers=None):
        return self.client.delete(
            f"/meeting-intelligence/action-items/{action_item_id}",
            headers=headers or self.owner_headers,
        )

    # ------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------

    def test_owner_can_generate_action_items(self):
        self._create_note("Discussed Q3 roadmap and budget.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            response = self._generate()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0]["task"], "Prepare Docker deployment")
        self.assertEqual(body[0]["assignee"], "John")
        self.assertEqual(body[0]["due_date"], "2026-08-01")
        self.assertEqual(body[0]["priority"], "High")
        self.assertEqual(body[0]["status"], "Pending")
        self.assertEqual(body[0]["meeting_id"], self.meeting_id)
        # Priority defaults to Medium when Gemini omits it.
        self.assertEqual(body[1]["assignee"], None)
        self.assertEqual(body[1]["priority"], "Low")

    def test_participant_cannot_generate_action_items(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            response = self._generate(headers=self.participant_headers)

        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_generate_action_items(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            response = self._generate(headers=self.outsider_headers)

        self.assertEqual(response.status_code, 403)

    def test_generate_action_items_meeting_not_found(self):
        response = self._generate(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_generate_action_items_missing_note(self):
        # Meeting exists but no note has been created yet.
        response = self._generate()
        self.assertEqual(response.status_code, 404)

    def test_generate_action_items_rejects_empty_note(self):
        self._create_note("Placeholder.")

        # Bypass the API's own blank-content validation to reach the
        # service-level defensive check (content stored directly via
        # the ORM as whitespace-only).
        db = self.SessionLocal()
        try:
            note = (
                db.query(MeetingNote)
                .filter(MeetingNote.meeting_id == self.meeting_id)
                .first()
            )
            note.content = "   "
            db.commit()
        finally:
            db.close()

        response = self._generate()
        self.assertEqual(response.status_code, 422)

    def test_generate_action_items_gemini_failure_isolated(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            first = self._generate()
        self.assertEqual(first.status_code, 200)

        with patch.object(
            GeminiService,
            "generate_json",
            side_effect=HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service unavailable.",
            ),
        ):
            failed = self._generate()
        self.assertEqual(failed.status_code, 503)

        # Existing action items must be unchanged after the failed
        # regenerate.
        unchanged = self._list()
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(len(unchanged.json()), 2)

    def test_generate_action_items_invalid_gemini_output_isolated(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            first = self._generate()
        self.assertEqual(first.status_code, 200)

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"unexpected": "shape"},
        ):
            failed = self._generate()
        self.assertEqual(failed.status_code, 502)

        unchanged = self._list()
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(len(unchanged.json()), 2)

    # ------------------------------------------------------------
    # Regenerate
    # ------------------------------------------------------------

    def test_owner_can_regenerate_action_items(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            first = self._generate()
        self.assertEqual(first.status_code, 200)

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={
                "action_items": [
                    {
                        "task": "Follow up with legal",
                        "assignee": "Amy",
                        "due_date": None,
                        "priority": "Medium",
                    }
                ]
            },
        ):
            second = self._generate()

        self.assertEqual(second.status_code, 200)
        body = second.json()
        # Old set fully replaced.
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["task"], "Follow up with legal")

    # ------------------------------------------------------------
    # View
    # ------------------------------------------------------------

    def test_owner_can_view_action_items(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            self._generate()

        response = self._list()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_participant_can_view_action_items(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            self._generate()

        response = self._list(headers=self.participant_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 2)

    def test_outsider_cannot_view_action_items(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            self._generate()

        response = self._list(headers=self.outsider_headers)
        self.assertEqual(response.status_code, 403)

    def test_view_action_items_meeting_not_found(self):
        response = self._list(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_view_action_items_missing_note(self):
        response = self._list()
        self.assertEqual(response.status_code, 404)

    def test_view_action_items_empty_before_generation(self):
        self._create_note("Discussed Q3 roadmap.")
        response = self._list()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # ------------------------------------------------------------
    # Update status
    # ------------------------------------------------------------

    def test_owner_can_update_status(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._update_status(item_id, "Completed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "Completed")

    def test_participant_cannot_update_status(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._update_status(
            item_id, "Completed", headers=self.participant_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_update_status(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._update_status(
            item_id, "Completed", headers=self.outsider_headers
        )
        self.assertEqual(response.status_code, 403)

    def test_update_status_item_not_found(self):
        response = self._update_status(999999, "Completed")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------

    def test_owner_can_delete_action_item(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._delete(item_id)
        self.assertEqual(response.status_code, 200)

        remaining = self._list()
        self.assertEqual(len(remaining.json()), 1)

    def test_participant_cannot_delete_action_item(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._delete(item_id, headers=self.participant_headers)
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_delete_action_item(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            generated = self._generate()
        item_id = generated.json()[0]["id"]

        response = self._delete(item_id, headers=self.outsider_headers)
        self.assertEqual(response.status_code, 403)

    def test_delete_action_item_not_found(self):
        response = self._delete(999999)
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------
    # Table ownership isolation (Meeting Intelligence V3 must never
    # read or write meeting_action_items, which remains exclusively
    # owned by the older AI pipeline).
    # ------------------------------------------------------------

    def test_generate_action_items_persists_only_to_owner_action_items_table(
        self,
    ):
        create_resp = self._create_note("Discussed Q3 roadmap.")
        note_id = create_resp.json()["id"]

        with patch.object(
            GeminiService, "generate_json", return_value=SAMPLE_GEMINI_OUTPUT,
        ):
            response = self._generate()
        self.assertEqual(response.status_code, 200)

        db = self.SessionLocal()
        try:
            owner_action_items = db.query(MeetingOwnerActionItem).all()
            legacy_action_items = db.query(MeetingActionItem).all()
        finally:
            db.close()

        self.assertEqual(len(owner_action_items), 2)
        self.assertTrue(
            all(item.meeting_note_id == note_id for item in owner_action_items)
        )
        # The legacy meeting_action_items table (older AI pipeline)
        # must remain completely untouched by this feature.
        self.assertEqual(len(legacy_action_items), 0)


if __name__ == "__main__":
    unittest.main()
