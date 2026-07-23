"""
Integration tests for Meeting Intelligence V2's HTTP surface
(POST/GET /meeting-intelligence/summary/{meeting_id}).

Mirrors tests/test_meeting_notes.py's harness: real FastAPI app via
TestClient, in-memory SQLite wired in through a get_db override.
GeminiService.generate_json is mocked via unittest.mock.patch.object,
mirroring tests/test_ai_voice_recipient_resolution.py.

Run with: python -m unittest tests.test_meeting_summary -v
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
from app.models.meeting_owner_note_summary import (  # noqa: E402
    MeetingOwnerNoteSummary,
)
from app.models.meeting_summary import MeetingSummary  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


class MeetingSummaryIntegrationTestCase(unittest.TestCase):

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
            f"/meeting-intelligence/summary/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    def _get(self, headers=None, meeting_id=None):
        return self.client.get(
            f"/meeting-intelligence/summary/{meeting_id or self.meeting_id}",
            headers=headers or self.owner_headers,
        )

    # ------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------

    def test_owner_can_generate_summary(self):
        self._create_note("Discussed Q3 roadmap and budget.")

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"summary": "Team reviewed the Q3 roadmap."},
        ):
            response = self._generate()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meeting_id"], self.meeting_id)
        self.assertEqual(body["summary"], "Team reviewed the Q3 roadmap.")

    def test_participant_cannot_generate_summary(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "Summary."},
        ):
            response = self._generate(headers=self.participant_headers)

        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_generate_summary(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "Summary."},
        ):
            response = self._generate(headers=self.outsider_headers)

        self.assertEqual(response.status_code, 403)

    def test_generate_summary_meeting_not_found(self):
        response = self._generate(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_generate_summary_missing_note(self):
        # Meeting exists but no note has been created yet.
        response = self._generate()
        self.assertEqual(response.status_code, 404)

    def test_generate_summary_rejects_empty_note(self):
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

    def test_generate_summary_gemini_failure_isolated(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"summary": "First summary."},
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

        # Existing summary must be unchanged after the failed regenerate.
        unchanged = self._get()
        self.assertEqual(unchanged.status_code, 200)
        self.assertEqual(unchanged.json()["summary"], "First summary.")

    def test_generate_summary_invalid_gemini_output_isolated(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={"summary": "First summary."},
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
        self.assertEqual(unchanged.json()["summary"], "First summary.")

    # ------------------------------------------------------------
    # Regenerate
    # ------------------------------------------------------------

    def test_owner_can_regenerate_summary(self):
        self._create_note("Discussed Q3 roadmap.")

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "First summary."},
        ):
            first = self._generate()
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "Regenerated summary."},
        ):
            second = self._generate()

        self.assertEqual(second.status_code, 200)
        body = second.json()
        # Same underlying row (upsert), content replaced.
        self.assertEqual(body["id"], first_id)
        self.assertEqual(body["summary"], "Regenerated summary.")

    # ------------------------------------------------------------
    # View
    # ------------------------------------------------------------

    def test_owner_can_view_summary(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "A summary."},
        ):
            self._generate()

        response = self._get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "A summary.")

    def test_participant_can_view_summary(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "A summary."},
        ):
            self._generate()

        response = self._get(headers=self.participant_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "A summary.")

    def test_outsider_cannot_view_summary(self):
        self._create_note("Discussed Q3 roadmap.")
        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "A summary."},
        ):
            self._generate()

        response = self._get(headers=self.outsider_headers)
        self.assertEqual(response.status_code, 403)

    def test_view_summary_meeting_not_found(self):
        response = self._get(meeting_id=999999)
        self.assertEqual(response.status_code, 404)

    def test_view_summary_not_generated_yet(self):
        self._create_note("Discussed Q3 roadmap.")
        response = self._get()
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------
    # Table ownership isolation (Meeting Intelligence V2 architecture
    # refactor: this feature must never read or write meeting_summaries,
    # which remains exclusively owned by the older AI pipeline).
    # ------------------------------------------------------------

    def test_generate_summary_persists_only_to_owner_note_summaries_table(self):
        create_resp = self._create_note("Discussed Q3 roadmap.")
        note_id = create_resp.json()["id"]

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "A summary."},
        ):
            response = self._generate()
        self.assertEqual(response.status_code, 200)

        db = self.SessionLocal()
        try:
            owner_note_summaries = db.query(MeetingOwnerNoteSummary).all()
            legacy_summaries = db.query(MeetingSummary).all()
        finally:
            db.close()

        self.assertEqual(len(owner_note_summaries), 1)
        self.assertEqual(owner_note_summaries[0].meeting_note_id, note_id)
        self.assertEqual(owner_note_summaries[0].summary, "A summary.")
        # The legacy meeting_summaries table (older AI pipeline) must
        # remain completely untouched by this feature.
        self.assertEqual(len(legacy_summaries), 0)

    def test_legacy_ai_summary_pipeline_unaffected_by_v2_generation(self):
        """
        Regression: the older AI Meeting Intelligence pipeline
        (POST /ai/meetings/{id}/summary, freeform notes text) must
        keep working exactly as before, and must not be able to see
        or be affected by anything V2 writes to
        meeting_owner_note_summaries, since the two tables are now
        fully separate.
        """
        self._create_note("Owner-authored note content.")

        with patch.object(
            GeminiService, "generate_json",
            return_value={"summary": "V2 summary."},
        ):
            v2_response = self._generate()
        self.assertEqual(v2_response.status_code, 200)

        with patch.object(
            GeminiService,
            "generate_json",
            return_value={
                "summary": "Legacy pipeline summary.",
                "action_items": [
                    {"task": "Follow up", "assignee": None, "due_date": None}
                ],
            },
        ):
            legacy_response = self.client.post(
                f"/ai/meetings/{self.meeting_id}/summary",
                json={"notes": "Freeform transcript text."},
                headers=self.owner_headers,
            )

        self.assertEqual(legacy_response.status_code, 200)
        legacy_body = legacy_response.json()
        self.assertEqual(legacy_body["summary"], "Legacy pipeline summary.")
        self.assertEqual(len(legacy_body["action_items"]), 1)

        # V2's own summary is unchanged by the legacy call.
        v2_after = self._get()
        self.assertEqual(v2_after.status_code, 200)
        self.assertEqual(v2_after.json()["summary"], "V2 summary.")

        # Legacy read endpoint reflects only the legacy pipeline's data.
        legacy_read = self.client.get(
            f"/meetings/{self.meeting_id}/summary",
            headers=self.owner_headers,
        )
        self.assertEqual(legacy_read.status_code, 200)
        self.assertEqual(
            legacy_read.json()["summary"], "Legacy pipeline summary."
        )

        db = self.SessionLocal()
        try:
            owner_note_summaries = db.query(MeetingOwnerNoteSummary).count()
            legacy_summaries = db.query(MeetingSummary).count()
        finally:
            db.close()

        self.assertEqual(owner_note_summaries, 1)
        self.assertEqual(legacy_summaries, 1)


if __name__ == "__main__":
    unittest.main()
