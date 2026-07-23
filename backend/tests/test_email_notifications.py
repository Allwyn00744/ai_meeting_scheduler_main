"""
Integration tests for the email notification gap fixed in this change:
previously, MeetingNotificationService.notify_meeting_created only
emailed participants/external guests, and MeetingCreate has no
participant_ids field - so a normal "create a meeting for myself"
request had zero recipients and silently sent nothing. Covers:

- the owner now gets a confirmation email on create (but not on
  update/cancel, where the owner is the one making the change)
- a participant added via POST /meetings/{id}/participants now gets an
  invitation email
- an SMTP outage never blocks meeting creation or participant add
- transient SMTP failures are retried; permanent ones are not

Mirrors the style of tests/test_whatsapp_notifications.py: a real
FastAPI app via starlette's TestClient, backed by an in-memory SQLite
DB. smtplib itself is globally stubbed out by tests/__init__.py; these
tests patch EmailService/smtplib locally where they need to observe or
control send behavior.

Run with: python -m unittest tests.test_email_notifications -v
(from the backend/ directory)
"""
import smtplib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402
from app.services.email_service import EmailService  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class EmailNotificationsTestCase(unittest.TestCase):

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
        token = login_resp.json()["access_token"]
        self.auth_headers = {"Authorization": f"Bearer {token}"}

        other_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Participant",
                "email": "participant@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(other_resp.status_code, 201)
        self.participant_id = other_resp.json()["id"]

    def _create_meeting(self, **overrides):
        payload = {
            "title": "Standup",
            "start_time": MEETING_START.isoformat(),
            "end_time": MEETING_END.isoformat(),
        }
        payload.update(overrides)
        resp = self.client.post(
            "/meetings/",
            json=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    # ---- owner confirmation on create ----

    def test_owner_is_emailed_on_create_with_no_participants(self):
        with patch(
            "app.services.email_service.EmailService.try_send_meeting_invitation",
            return_value=True,
        ) as mock_send:
            self._create_meeting()

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["to_email"], "owner@example.com")

    def test_owner_and_external_guest_are_both_emailed_on_create(self):
        with patch(
            "app.services.email_service.EmailService.try_send_meeting_invitation",
            return_value=True,
        ) as mock_send:
            self._create_meeting(external_guest_emails=["guest@example.com"])

        recipients = {
            call.kwargs["to_email"] for call in mock_send.call_args_list
        }
        self.assertEqual(recipients, {"owner@example.com", "guest@example.com"})

    def test_owner_not_double_counted_if_also_a_guest(self):
        with patch(
            "app.services.email_service.EmailService.try_send_meeting_invitation",
            return_value=True,
        ) as mock_send:
            self._create_meeting(external_guest_emails=["owner@example.com"])

        self.assertEqual(mock_send.call_count, 1)

    def test_email_outage_does_not_block_meeting_creation(self):
        # Patches send_email (which does raise) rather than
        # try_send_meeting_invitation (which never raises by contract -
        # see EmailService.try_send_meeting_invitation's docstring) so
        # this exercises the real resilience path: the try_* wrapper
        # catching a real SMTP failure, not a mock breaking the
        # wrapper's own contract.
        with patch(
            "app.services.email_service.EmailService.send_email",
            side_effect=Exception("smtp down"),
        ):
            # _create_meeting already asserts status_code == 201
            self._create_meeting()

    # ---- owner is NOT emailed on update/cancel (only participants/guests) ----

    def test_owner_not_emailed_on_update_with_no_participants(self):
        meeting_id = self._create_meeting()  # sends the owner one create email

        with patch(
            "app.services.email_service.EmailService.try_send_meeting_update",
        ) as mock_update:
            resp = self.client.put(
                f"/meetings/{meeting_id}",
                json={"title": "Standup (renamed)"},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 200)
        mock_update.assert_not_called()

    # ---- participant invite on POST /meetings/{id}/participants ----

    def test_adding_participant_sends_invitation_email(self):
        meeting_id = self._create_meeting()

        with patch(
            "app.services.email_service.EmailService.try_send_meeting_invitation",
            return_value=True,
        ) as mock_send:
            resp = self.client.post(
                f"/meetings/{meeting_id}/participants",
                json={"user_id": self.participant_id},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 201)
        mock_send.assert_called_once()
        self.assertEqual(
            mock_send.call_args.kwargs["to_email"], "participant@example.com",
        )
        self.assertIn("Standup", mock_send.call_args.kwargs["meeting_title"])

    def test_participant_invite_outage_does_not_block_add_participant(self):
        meeting_id = self._create_meeting()

        # Patches send_email (which does raise), not
        # try_send_meeting_invitation - see the equivalent note on
        # test_email_outage_does_not_block_meeting_creation above.
        with patch(
            "app.services.email_service.EmailService.send_email",
            side_effect=Exception("smtp down"),
        ):
            resp = self.client.post(
                f"/meetings/{meeting_id}/participants",
                json={"user_id": self.participant_id},
                headers=self.auth_headers,
            )

        self.assertEqual(resp.status_code, 201)

    # ---- retry behavior (EmailService.send_email / smtplib) ----

    def test_transient_smtp_error_is_retried_then_succeeds(self):
        mock_smtp_instance = MagicMock()
        mock_smtp_instance.__enter__.return_value = mock_smtp_instance
        mock_smtp_instance.__exit__.return_value = False

        # First two attempts fail with a transport-level error; the
        # third (final, allowed) attempt succeeds - proves the retry
        # wrapper in email_service.py's _send_smtp_with_retry recovers
        # instead of giving up on the first transient hiccup.
        call_count = {"n": 0}

        def _flaky_smtp(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise smtplib.SMTPServerDisconnected("connection lost")
            return mock_smtp_instance

        with patch("smtplib.SMTP", side_effect=_flaky_smtp):
            EmailService.send_email(
                to_email="someone@example.com",
                subject="Test",
                body="Body",
            )

        self.assertEqual(call_count["n"], 3)
        mock_smtp_instance.send_message.assert_called_once()

    def test_permanent_smtp_auth_error_is_not_retried(self):
        call_count = {"n": 0}

        def _always_fails_auth(*args, **kwargs):
            call_count["n"] += 1
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

        with patch("smtplib.SMTP", side_effect=_always_fails_auth):
            with self.assertRaises(smtplib.SMTPAuthenticationError):
                EmailService.send_email(
                    to_email="someone@example.com",
                    subject="Test",
                    body="Body",
                )

        # Not retried: an auth rejection is permanent, so a single
        # attempt is expected instead of the 3-attempt transient path.
        self.assertEqual(call_count["n"], 1)


if __name__ == "__main__":
    unittest.main()
