"""
Integration tests for Meeting Intelligence V4's HTTP surface
(POST/GET /meeting-intelligence/follow-up/{meeting_id}).

Mirrors tests/test_meeting_summary.py's harness: real FastAPI app via
TestClient, in-memory SQLite wired in through a get_db override.
GeminiService.generate_json is mocked via unittest.mock.patch.object.

Run with: python -m unittest tests.test_meeting_followup_email -v
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
from app.models.meeting_owner_followup_email import (  # noqa: E402
    MeetingOwnerFollowUpEmail,
)
from app.services.gemini_service import GeminiService  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


class MeetingFollowUpEmailIntegrationTestCase(unittest.TestCase):

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
                "title": "Sprint Planning",
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

    def _create_summary(self, summary_text="Team reviewed the Q3 roadmap."):
        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": summary_text},
        ):
            resp = self.client.post(
                f"/meeting-intelligence/summary/{self.meeting_id}",
                headers=self.owner_headers,
            )
        self.assertEqual(resp.status_code, 200)
        return resp

    def _create_action_items(self):
        with patch.object(
            GeminiService, "generate_json",
            return_value={
                "action_items": [
                    {
                        "task": "Send budget doc",
                        "assignee": "Alice",
                        "due_date": "2026-08-05",
                        "priority": "High",
                    }
                ]
            },
        ):
            resp = self.client.post(
                f"/meeting-intelligence/action-items/{self.meeting_id}",
                headers=self.owner_headers,
            )
        self.assertEqual(resp.status_code, 200)
        return resp

    def _generate(self, headers=None, meeting_id=None):
        return self.client.post(
            f"/meeting-intelligence/follow-up/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    def _get(self, headers=None, meeting_id=None):
        return self.client.get(
            f"/meeting-intelligence/follow-up/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    # ------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------

    def test_owner_can_generate_followup_email(self):
        self._create_note("Discussed Q3 roadmap and budget.")
        self._create_summary("Team reviewed the Q3 roadmap and budget.")

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={
                "subject": "Sprint Planning Follow-up",
                "body": "Hello Team, thanks for joining today...",
            },
        ):
            response = self._generate()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meeting_id"], self.meeting_id)
        self.assertEqual(body["subject"], "Sprint Planning Follow-up")
        self.assertEqual(
            body["body"], "Hello Team, thanks for joining today..."
        )

    def test_generate_followup_email_includes_action_items_when_present(
        self,
    ):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary("Team reviewed the Q3 roadmap.")
        self._create_action_items()

        captured_prompts = []

        def fake_generate_json(prompt):
            captured_prompts.append(prompt)
            return {"subject": "Subject", "body": "Body"}

        with patch.object(
            GeminiService, "generate_json", side_effect=fake_generate_json,
        ):
            response = self._generate()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("Send budget doc", captured_prompts[0])
        self.assertIn("Alice", captured_prompts[0])

    def test_generate_followup_email_without_action_items(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary("Team reviewed the Q3 roadmap.")

        captured_prompts = []

        def fake_generate_json(prompt):
            captured_prompts.append(prompt)
            return {"subject": "Subject", "body": "Body"}

        with patch.object(
            GeminiService, "generate_json", side_effect=fake_generate_json,
        ):
            response = self._generate()

        self.assertEqual(response.status_code, 200)
        self.assertIn("none were recorded", captured_prompts[0])

    def test_participant_cannot_generate_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            response = self._generate(headers=self.participant_headers)

        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_generate_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            response = self._generate(headers=self.outsider_headers)

        self.assertEqual(response.status_code, 403)

    def test_generate_followup_email_meeting_not_found(self):
        response = self._generate(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_generate_followup_email_missing_note(self):
        # Meeting exists but no note has been created yet.
        response = self._generate()
        self.assertEqual(response.status_code, 404)

    def test_generate_followup_email_missing_summary(self):
        # Note exists but no summary has been generated yet.
        self._create_note("Discussed Q3 roadmap.")
        response = self._generate()
        self.assertEqual(response.status_code, 404)

    def test_generate_followup_email_gemini_failure_isolated(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"subject": "First subject", "body": "First body"},
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

        # Existing follow-up email must be unchanged after the failed
        # regenerate.
        unchanged = self._get()
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(unchanged.json()["subject"], "First subject")

    def test_generate_followup_email_invalid_gemini_output_isolated(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"subject": "First subject", "body": "First body"},
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

        unchanged = self._get()
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(unchanged.json()["subject"], "First subject")

    # ------------------------------------------------------------
    # Regenerate
    # ------------------------------------------------------------

    def test_owner_can_regenerate_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "First", "body": "First body"},
        ):
            first = self._generate()
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "Regenerated", "body": "New body"},
        ):
            second = self._generate()

        self.assertEqual(second.status_code, 200)
        body = second.json()
        # Same underlying row (upsert), content replaced.
        self.assertEqual(body["id"], first_id)
        self.assertEqual(body["subject"], "Regenerated")
        self.assertEqual(body["body"], "New body")

    # ------------------------------------------------------------
    # View
    # ------------------------------------------------------------

    def test_owner_can_view_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()
        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            self._generate()

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["subject"], "S")

    def test_participant_can_view_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()
        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            self._generate()

        response = self._get(headers=self.participant_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["subject"], "S")

    def test_outsider_cannot_view_followup_email(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()
        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            self._generate()

        response = self._get(headers=self.outsider_headers)
        self.assertEqual(response.status_code, 403)

    def test_view_followup_email_meeting_not_found(self):
        response = self._get(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_view_followup_email_not_generated_yet(self):
        self._create_note("Discussed Q3 roadmap.")
        self._create_summary()
        response = self._get()
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------
    # Table ownership isolation (Meeting Intelligence V4 must never
    # touch any legacy AI pipeline model/table/route, nor be touched
    # by them).
    # ------------------------------------------------------------

    def test_generate_followup_email_persists_only_to_owner_followup_table(
        self,
    ):
        create_resp = self._create_note("Discussed Q3 roadmap.")
        note_id = create_resp.json()["id"]
        self._create_summary()

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "S", "body": "B"},
        ):
            response = self._generate()
        self.assertEqual(response.status_code, 200)

        db = self.SessionLocal()
        try:
            followup_rows = db.query(MeetingOwnerFollowUpEmail).all()
        finally:
            db.close()

        self.assertEqual(len(followup_rows), 1)
        self.assertEqual(followup_rows[0].meeting_note_id, note_id)
        self.assertEqual(followup_rows[0].subject, "S")
        self.assertEqual(followup_rows[0].body, "B")

    def test_legacy_ai_followup_pipeline_unaffected_by_v4_generation(self):
        """
        Regression: the older AI Meeting Intelligence pipeline's
        follow-up draft (POST /ai/meetings/{id}/follow-up, freeform
        notes text) must keep working exactly as before - draft-only,
        never persisted - and must be completely unaffected by
        anything V4 writes to meeting_owner_followup_emails.
        """
        self._create_note("Owner-authored note content.")
        self._create_summary("V4 summary.")

        with patch.object(
            GeminiService, "generate_json",
            return_value={"subject": "V4 subject", "body": "V4 body"},
        ):
            v4_response = self._generate()
        self.assertEqual(v4_response.status_code, 200)

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={
                "email_subject": "Legacy subject",
                "email_body": "Legacy body",
            },
        ):
            legacy_response = self.client.post(
                f"/ai/meetings/{self.meeting_id}/follow-up",
                json={"notes": "Freeform transcript text."},
                headers=self.owner_headers,
            )

        self.assertEqual(legacy_response.status_code, 200)
        legacy_body = legacy_response.json()
        self.assertEqual(legacy_body["email_subject"], "Legacy subject")
        self.assertEqual(legacy_body["email_body"], "Legacy body")

        # V4's own persisted email is unchanged by the legacy call.
        v4_after = self._get()
        self.assertEqual(v4_after.status_code, 200)
        self.assertEqual(v4_after.json()["subject"], "V4 subject")

        db = self.SessionLocal()
        try:
            followup_rows = db.query(MeetingOwnerFollowUpEmail).count()
        finally:
            db.close()

        # The legacy endpoint never persists anything - only V4's one
        # generated row should exist.
        self.assertEqual(followup_rows, 1)


if __name__ == "__main__":
    unittest.main()
