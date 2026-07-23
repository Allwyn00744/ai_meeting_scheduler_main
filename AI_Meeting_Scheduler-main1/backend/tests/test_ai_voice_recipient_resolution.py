"""
Focused tests for AI text + Voice scheduling recipient resolution
(V1 fix).

Exercises AIMeetingService.schedule_from_text and schedule_from_voice
end-to-end through the real SchedulerService/ExternalGuestService/
ConflictService orchestration logic. Only I/O boundaries are mocked:
Gemini (text generation + transcription), the database repositories,
Google Calendar, and SMTP. Follows the same pattern as
tests/test_redis_cache.py (unittest, MagicMock db, patch.object on
repository static methods).

Two TestCases share one fixture base:
  - AITextSchedulingRecipientResolutionTestCase: the POST
    /ai/schedule-text path (schedule_from_text called directly).
  - AIVoiceSchedulingRecipientResolutionTestCase: the POST
    /ai/schedule-voice path (schedule_from_voice), confirming it
    delegates to schedule_from_text exactly once and inherits the
    identical resolution behavior rather than duplicating it.

Run with: python -m unittest tests.test_ai_voice_recipient_resolution -v
(from the backend/ directory)
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

# Importing app.db.base registers every mapped model up front so
# SQLAlchemy can resolve string-based relationship() references
# before any model is instantiated below (mirrors test_redis_cache.py).
from app.db.base import Base  # noqa: E402,F401
from app.repositories.external_meeting_guest_repository import (  # noqa: E402
    ExternalMeetingGuestRepository,
)
from app.repositories.meeting_participant_repository import (  # noqa: E402
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.ai_meeting_service import AIMeetingService  # noqa: E402
from app.services.availability_service import AvailabilityService  # noqa: E402
from app.services.email_service import EmailService  # noqa: E402
from app.services.gemini_service import GeminiService  # noqa: E402
from app.services.google_calendar_service import (  # noqa: E402
    GoogleCalendarService,
)


class FakeUser:
    def __init__(self, id, email, timezone="UTC", name="Test User"):
        self.id = id
        self.email = email
        self.timezone = timezone
        self.name = name


def _raw_intent(
    title="Project review",
    start_time="2026-07-15T15:00:00Z",
    duration_minutes=60,
    participant_ids=None,
    external_guest_emails=None,
):
    return {
        "status": "ok",
        "title": title,
        "description": None,
        "start_time": start_time,
        "end_time": None,
        "duration_minutes": duration_minutes,
        "location": None,
        "participant_ids": participant_ids or [],
        "external_guest_emails": external_guest_emails or [],
        "repeat": False,
        "repeat_type": None,
        "occurrences": None,
    }


class _BaseRecipientResolutionTestCase(unittest.TestCase):
    """
    Shared fixture: a fake owner, a fake registered user (mixed-case
    email, to prove case-insensitive DB resolution), and mocked
    repository/provider boundaries so SchedulerService's real
    business logic (participant validation, external guest
    resolution, conflict/availability checks, meeting creation,
    best-effort notification) runs against them exactly as it would
    against PostgreSQL. Has no test_* methods itself - only
    subclasses contribute tests.
    """

    def setUp(self):
        self.db = MagicMock()

        self.owner = FakeUser(id=1, email="owner@example.com")
        self.registered = FakeUser(id=5, email="John@Example.com")

        self.users_by_id = {
            self.owner.id: self.owner,
            self.registered.id: self.registered,
        }
        self.users_by_email = {
            self.owner.email.lower(): self.owner,
            self.registered.email.lower(): self.registered,
        }

        self.next_meeting_id = 100
        self.created_meetings = []
        self.created_participants = []
        self.created_guests = []

        patches = [
            patch.object(
                UserRepository,
                "get_user_by_id",
                side_effect=lambda db, uid: self.users_by_id.get(uid),
            ),
            patch.object(
                UserRepository,
                "get_user_by_email_ci",
                side_effect=lambda db, email: self.users_by_email.get(
                    email.strip().lower()
                ),
            ),
            patch.object(
                UserRepository,
                "get_users_by_ids",
                side_effect=lambda db, ids: [
                    self.users_by_id[i] for i in ids if i in self.users_by_id
                ],
            ),
            patch.object(
                MeetingRepository,
                "get_user_meetings",
                return_value=[],
            ),
            patch.object(
                MeetingRepository,
                "create",
                side_effect=self._fake_create_meeting,
            ),
            patch.object(
                MeetingParticipantRepository,
                "create_many",
                side_effect=self._fake_create_participants,
            ),
            patch.object(
                ExternalMeetingGuestRepository,
                "create_many",
                side_effect=self._fake_create_guests,
            ),
            patch.object(
                AvailabilityService,
                "is_user_available",
                return_value=True,
            ),
            patch.object(
                GoogleCalendarService,
                "create_google_calendar_event",
                return_value={
                    "id": "evt-1",
                    "htmlLink": "https://calendar.example/evt-1",
                    "hangoutLink": "https://meet.example/evt-1",
                },
            ),
            patch(
                "app.services.scheduler_service.cache_delete_prefix",
            ),
            patch("app.services.scheduler_service.cache_delete"),
        ]

        for p in patches:
            self.addCleanup(p.stop)
            p.start()

    def _fake_create_meeting(self, db, meeting):
        meeting.id = self.next_meeting_id
        self.next_meeting_id += 1
        self.created_meetings.append(meeting)
        return meeting

    def _fake_create_participants(self, db, participants):
        self.created_participants.extend(participants)
        return participants

    def _fake_create_guests(self, db, guests):
        self.created_guests.extend(guests)
        return guests


class AITextSchedulingRecipientResolutionTestCase(
    _BaseRecipientResolutionTestCase
):
    """POST /ai/schedule-text path: AIMeetingService.schedule_from_text."""

    def _schedule(self, raw_response):
        with patch.object(
            GeminiService, "generate_json", return_value=raw_response
        ):
            return AIMeetingService.schedule_from_text(
                self.db, "irrelevant - Gemini is mocked", self.owner
            )

    # ------------------------------------------------------------------
    # 1. Registered participant email
    # ------------------------------------------------------------------
    def test_registered_email_resolves_to_participant_and_notifies_once(self):
        raw = _raw_intent(external_guest_emails=["john@example.com"])

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            result = self._schedule(raw)

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(
            [p.user_id for p in self.created_participants], [5]
        )
        self.assertEqual(self.created_guests, [])

        spy.assert_called_once()
        self.assertEqual(spy.call_args.kwargs["to_email"], "John@Example.com")

    # ------------------------------------------------------------------
    # 2. Unregistered email
    # ------------------------------------------------------------------
    def test_unregistered_email_persisted_as_external_guest_and_notified_once(
        self,
    ):
        raw = _raw_intent(external_guest_emails=["guest@example.com"])

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            result = self._schedule(raw)

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(self.created_participants, [])
        self.assertEqual(
            [g.email for g in self.created_guests], ["guest@example.com"]
        )

        spy.assert_called_once()
        self.assertEqual(
            spy.call_args.kwargs["to_email"], "guest@example.com"
        )

    # ------------------------------------------------------------------
    # 3. Mixed registered/unregistered emails
    # ------------------------------------------------------------------
    def test_mixed_emails_split_correctly_with_one_email_each(self):
        raw = _raw_intent(
            external_guest_emails=[
                "john@example.com",
                "guest@example.com",
            ]
        )

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            self._schedule(raw)

        self.assertEqual(
            [p.user_id for p in self.created_participants], [5]
        )
        self.assertEqual(
            [g.email for g in self.created_guests], ["guest@example.com"]
        )

        self.assertEqual(spy.call_count, 2)
        recipients = {c.kwargs["to_email"] for c in spy.call_args_list}
        self.assertEqual(
            recipients, {"John@Example.com", "guest@example.com"}
        )

    # ------------------------------------------------------------------
    # 4. Case-insensitive duplicate emails
    # ------------------------------------------------------------------
    def test_case_insensitive_duplicate_emails_are_deduplicated(self):
        raw = _raw_intent(
            external_guest_emails=[
                "Guest@Example.com",
                "guest@example.com",
                "GUEST@EXAMPLE.COM",
            ]
        )

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            self._schedule(raw)

        self.assertEqual(len(self.created_guests), 1)
        self.assertEqual(self.created_guests[0].email, "guest@example.com")
        spy.assert_called_once()

    # ------------------------------------------------------------------
    # 5. Explicit numeric participant ID still works
    # ------------------------------------------------------------------
    def test_explicit_numeric_participant_id_still_works(self):
        raw = _raw_intent(participant_ids=[5])

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            self._schedule(raw)

        self.assertEqual(
            [p.user_id for p in self.created_participants], [5]
        )
        spy.assert_called_once()
        self.assertEqual(spy.call_args.kwargs["to_email"], "John@Example.com")

    # ------------------------------------------------------------------
    # 6. Overlap: explicit participant ID + same user's email
    # ------------------------------------------------------------------
    def test_explicit_id_and_same_users_email_overlap_to_one_participant(
        self,
    ):
        raw = _raw_intent(
            participant_ids=[5],
            external_guest_emails=["john@example.com"],
        )

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            self._schedule(raw)

        self.assertEqual(
            [p.user_id for p in self.created_participants], [5]
        )
        self.assertEqual(self.created_guests, [])
        spy.assert_called_once()

    # ------------------------------------------------------------------
    # 7. No-recipient AI request
    # ------------------------------------------------------------------
    def test_no_recipient_request_still_schedules_with_zero_invitations(self):
        raw = _raw_intent()

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as spy:
            result = self._schedule(raw)

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(self.created_participants, [])
        self.assertEqual(self.created_guests, [])
        spy.assert_not_called()

    # ------------------------------------------------------------------
    # 10. Invalid email extracted by AI
    # ------------------------------------------------------------------
    def test_invalid_extracted_email_is_rejected_without_persisting_anything(
        self,
    ):
        raw = _raw_intent(external_guest_emails=["not-an-email"])

        with self.assertRaises(HTTPException) as ctx:
            self._schedule(raw)

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(self.created_meetings, [])
        self.assertEqual(self.created_guests, [])

    # ------------------------------------------------------------------
    # 11. SMTP failure isolation
    # ------------------------------------------------------------------
    def test_smtp_failure_does_not_fail_the_scheduling_request(self):
        raw = _raw_intent(external_guest_emails=["guest@example.com"])

        with patch.object(
            EmailService,
            "send_meeting_invitation",
            side_effect=OSError("simulated SMTP outage"),
        ):
            result = self._schedule(raw)

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(
            [g.email for g in self.created_guests], ["guest@example.com"]
        )


class AIVoiceSchedulingRecipientResolutionTestCase(
    _BaseRecipientResolutionTestCase
):
    """
    POST /ai/schedule-voice path: AIMeetingService.schedule_from_voice.

    schedule_from_voice transcribes audio then calls schedule_from_text
    exactly once - no scheduling or recipient-resolution logic is
    duplicated there. These tests confirm that inheritance holds for
    both a registered-user email and an external guest email
    extracted from the transcript, with Gemini's transcription and
    JSON-generation calls mocked (no real speech/LLM provider is ever
    called).
    """

    def _schedule_from_voice(self, transcript_text, raw_response):
        with patch.object(
            GeminiService, "transcribe_audio", return_value=transcript_text
        ) as transcribe_spy, patch.object(
            GeminiService, "generate_json", return_value=raw_response
        ), patch.object(
            AIMeetingService,
            "schedule_from_text",
            wraps=AIMeetingService.schedule_from_text,
        ) as schedule_from_text_spy:
            result = AIMeetingService.schedule_from_voice(
                self.db, b"fake-audio-bytes", "audio/webm", self.owner
            )
        return result, transcribe_spy, schedule_from_text_spy

    # ------------------------------------------------------------------
    # 8. Voice + registered participant email
    # ------------------------------------------------------------------
    def test_voice_registered_email_resolves_and_notifies_once(self):
        raw = _raw_intent(external_guest_emails=["john@example.com"])

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as email_spy:
            result, transcribe_spy, schedule_spy = self._schedule_from_voice(
                "Schedule a sync tomorrow at 3pm with john@example.com", raw
            )

        transcribe_spy.assert_called_once()
        schedule_spy.assert_called_once()

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(
            [p.user_id for p in self.created_participants], [5]
        )
        self.assertEqual(self.created_guests, [])
        email_spy.assert_called_once()
        self.assertEqual(
            email_spy.call_args.kwargs["to_email"], "John@Example.com"
        )

    # ------------------------------------------------------------------
    # 9. Voice + external guest email
    # ------------------------------------------------------------------
    def test_voice_external_guest_email_resolves_and_notifies_once(self):
        raw = _raw_intent(external_guest_emails=["outsider@example.com"])

        with patch.object(
            EmailService, "try_send_meeting_invitation", return_value=True
        ) as email_spy:
            result, transcribe_spy, schedule_spy = self._schedule_from_voice(
                "Schedule a sync tomorrow at 3pm with outsider@example.com",
                raw,
            )

        transcribe_spy.assert_called_once()
        schedule_spy.assert_called_once()

        self.assertEqual(result["meeting_ids"], [100])
        self.assertEqual(self.created_participants, [])
        self.assertEqual(
            [g.email for g in self.created_guests], ["outsider@example.com"]
        )
        email_spy.assert_called_once()
        self.assertEqual(
            email_spy.call_args.kwargs["to_email"], "outsider@example.com"
        )


if __name__ == "__main__":
    unittest.main()
