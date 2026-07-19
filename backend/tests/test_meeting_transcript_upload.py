"""
Integration tests for AI Transcript Upload
(POST /meeting-intelligence/transcript/{meeting_id}).

Exercises the real FastAPI app end-to-end through starlette's
TestClient: register -> login -> create meeting -> upload transcript,
mirroring tests/test_meeting_notes.py's setup. The only substitution is
the DB itself (in-memory SQLite instead of the configured PostgreSQL),
wired in via a dependency_overrides on get_db.

Run with: python -m unittest tests.test_meeting_transcript_upload -v
(from the backend/ directory)
"""
import io
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import docx  # noqa: E402  (python-docx)
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

UPLOAD_URL_TEMPLATE = "/meeting-intelligence/transcript/{meeting_id}"


def _build_docx_bytes(text: str) -> bytes:
    document = docx.Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _build_pdf_bytes(text: str | None) -> bytes:
    """
    Hand-builds a minimal single-page PDF with a valid xref table so
    pdfplumber can parse it without any PDF-writing dependency. When
    text is None, the content stream draws nothing (no Tj operator),
    simulating a scanned/image-only page with no extractable text.
    """
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/Resources<</Font<</F1 4 0 R>>>>"
        b"/MediaBox[0 0 300 300]/Contents 5 0 R>>",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    stream_body = (
        f"BT /F1 18 Tf 20 150 Td ({text}) Tj ET".encode("latin-1")
        if text is not None
        else b"BT ET"
    )
    objects.append(
        b"<</Length %d>>\nstream\n" % len(stream_body)
        + stream_body
        + b"\nendstream"
    )

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(obj)
        out.write(b"\nendobj\n")

    xref_offset = out.tell()
    n = len(objects) + 1
    out.write(f"xref\n0 {n}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(b"trailer\n")
    out.write(f"<</Size {n}/Root 1 0 R>>\n".encode())
    out.write(b"startxref\n")
    out.write(f"{xref_offset}\n".encode())
    out.write(b"%%EOF")
    return out.getvalue()


class MeetingTranscriptUploadIntegrationTestCase(unittest.TestCase):

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

        self.upload_url = UPLOAD_URL_TEMPLATE.format(
            meeting_id=self.meeting_id
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

    def _upload(
        self,
        url,
        filename,
        content,
        content_type,
        headers=None,
    ):
        return self.client.post(
            url,
            files={"file": (filename, content, content_type)},
            headers=headers if headers is not None else self.owner_headers,
        )

    # ------------------------------------------------------------
    # TXT upload
    # ------------------------------------------------------------

    def test_owner_can_upload_txt_transcript_creates_note(self):
        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"  Discussed Q3 roadmap and next steps.  ",
            "text/plain",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["meeting_id"], self.meeting_id)
        self.assertEqual(
            body["content"], "Discussed Q3 roadmap and next steps."
        )
        self.assertEqual(body["created_by_id"], self.owner_id)

    # ------------------------------------------------------------
    # DOCX upload
    # ------------------------------------------------------------

    def test_owner_can_upload_docx_transcript_creates_note(self):
        docx_bytes = _build_docx_bytes("Discussed the roadmap in DOCX form.")

        response = self._upload(
            self.upload_url,
            "transcript.docx",
            docx_bytes,
            (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"],
            "Discussed the roadmap in DOCX form.",
        )

    # ------------------------------------------------------------
    # PDF upload
    # ------------------------------------------------------------

    def test_owner_can_upload_pdf_transcript_creates_note(self):
        pdf_bytes = _build_pdf_bytes("Hello PDF Transcript")

        response = self._upload(
            self.upload_url,
            "transcript.pdf",
            pdf_bytes,
            "application/pdf",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"], "Hello PDF Transcript"
        )

    def test_scanned_pdf_with_no_extractable_text_rejected(self):
        pdf_bytes = _build_pdf_bytes(None)

        response = self._upload(
            self.upload_url,
            "scanned.pdf",
            pdf_bytes,
            "application/pdf",
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("scanned", response.json()["detail"].lower())

    # ------------------------------------------------------------
    # Empty file
    # ------------------------------------------------------------

    def test_empty_file_rejected(self):
        response = self._upload(
            self.upload_url,
            "empty.txt",
            b"",
            "text/plain",
        )

        self.assertEqual(response.status_code, 422)

    def test_whitespace_only_file_rejected(self):
        response = self._upload(
            self.upload_url,
            "blank.txt",
            b"   \n\t  ",
            "text/plain",
        )

        self.assertEqual(response.status_code, 422)

    # ------------------------------------------------------------
    # Unsupported extension
    # ------------------------------------------------------------

    def test_unsupported_extension_rejected(self):
        response = self._upload(
            self.upload_url,
            "transcript.png",
            b"not really an image",
            "image/png",
        )

        self.assertEqual(response.status_code, 415)

    def test_octet_stream_rejected_when_extension_unsupported(self):
        response = self._upload(
            self.upload_url,
            "transcript.exe",
            b"binary content",
            "application/octet-stream",
        )

        self.assertEqual(response.status_code, 415)

    def test_octet_stream_accepted_when_extension_supported(self):
        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"Notes sent with a generic content type.",
            "application/octet-stream",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"],
            "Notes sent with a generic content type.",
        )

    # ------------------------------------------------------------
    # Oversized file
    # ------------------------------------------------------------

    def test_oversized_file_rejected(self):
        oversized_content = b"a" * (5 * 1024 * 1024 + 1)

        response = self._upload(
            self.upload_url,
            "huge.txt",
            oversized_content,
            "text/plain",
        )

        self.assertEqual(response.status_code, 413)

    # ------------------------------------------------------------
    # Owner authorization / participant forbidden
    # ------------------------------------------------------------

    def test_participant_cannot_upload_transcript(self):
        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"Participant trying to upload.",
            "text/plain",
            headers=self.participant_headers,
        )

        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_upload_transcript(self):
        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"Outsider trying to upload.",
            "text/plain",
            headers=self.outsider_headers,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------
    # Meeting not found
    # ------------------------------------------------------------

    def test_meeting_not_found(self):
        response = self._upload(
            UPLOAD_URL_TEMPLATE.format(meeting_id=999999),
            "transcript.txt",
            b"Note for a ghost meeting.",
            "text/plain",
        )

        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------
    # Overwrite existing note / create new note
    # ------------------------------------------------------------

    def test_upload_overwrites_existing_note(self):
        create_note_resp = self.client.post(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            json={"content": "Original owner-typed note."},
            headers=self.owner_headers,
        )
        self.assertEqual(create_note_resp.status_code, 201)
        note_id = create_note_resp.json()["id"]

        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"Replacement transcript content.",
            "text/plain",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], note_id)
        self.assertEqual(body["content"], "Replacement transcript content.")

        get_resp = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.json()["content"], "Replacement transcript content.")

    def test_upload_creates_note_when_none_exists(self):
        get_resp = self.client.get(
            f"/meeting-intelligence/notes/{self.meeting_id}",
            headers=self.owner_headers,
        )
        self.assertEqual(get_resp.status_code, 404)

        response = self._upload(
            self.upload_url,
            "transcript.txt",
            b"Brand new transcript note.",
            "text/plain",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["content"], "Brand new transcript note."
        )

    def test_second_transcript_upload_overwrites_first(self):
        first = self._upload(
            self.upload_url,
            "first.txt",
            b"First transcript.",
            "text/plain",
        )
        self.assertEqual(first.status_code, 200)
        note_id = first.json()["id"]

        second = self._upload(
            self.upload_url,
            "second.txt",
            b"Second transcript.",
            "text/plain",
        )

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["id"], note_id)
        self.assertEqual(second.json()["content"], "Second transcript.")


if __name__ == "__main__":
    unittest.main()
