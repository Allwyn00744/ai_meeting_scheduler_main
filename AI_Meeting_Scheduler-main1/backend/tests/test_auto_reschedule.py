"""
Focused tests for SchedulerService.auto_reschedule_meeting (Auto
Rescheduling V1).

Exercises the real SchedulerService/MeetingService orchestration
(slot search across owner + participant + resource conflicts and
availability, owner-only authorization, persistence via the same
update_meeting path used by a manual PUT /meetings/{id} edit) against
an in-memory fake meeting store. Only I/O boundaries are mocked: the
repositories, Google Calendar, and SMTP - follows the same pattern as
tests/test_ai_voice_recipient_resolution.py (unittest, MagicMock db,
patch.object on repository/service static methods).

Run with: python -m unittest tests.test_auto_reschedule -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import HTTPException  # noqa: E402

# Importing app.db.base registers every mapped model up front so
# SQLAlchemy can resolve string-based relationship() references
# before any model is instantiated below (mirrors test_redis_cache.py
# and test_ai_voice_recipient_resolution.py).
from app.db.base import Base  # noqa: E402,F401
from app.repositories.external_meeting_guest_repository import (  # noqa: E402
    ExternalMeetingGuestRepository,
)
from app.repositories.meeting_participant_repository import (  # noqa: E402
    MeetingParticipantRepository,
)
from app.repositories.meeting_repository import MeetingRepository  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.analytics_service import AnalyticsService  # noqa: E402
from app.services.availability_service import AvailabilityService  # noqa: E402
from app.services.email_service import EmailService  # noqa: E402
from app.services.google_calendar_service import (  # noqa: E402
    GoogleCalendarService,
)
from app.services.scheduler_service import SchedulerService  # noqa: E402

MEETING_START = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)
STEP = timedelta(minutes=15)


class FakeUser:
    def __init__(self, id, email, timezone="UTC"):
        self.id = id
        self.email = email
        self.timezone = timezone


class FakeMeeting:
    def __init__(
        self,
        id,
        owner_id,
        start_time=MEETING_START,
        end_time=MEETING_END,
        resource_id=None,
        google_event_id=None,
        outlook_event_id=None,
        zoom_meeting_id=None,
        status="scheduled",
        title="Sync",
    ):
        self.id = id
        self.owner_id = owner_id
        self.start_time = start_time
        self.end_time = end_time
        self.resource_id = resource_id
        self.google_event_id = google_event_id
        self.outlook_event_id = outlook_event_id
        self.zoom_meeting_id = zoom_meeting_id
        self.zoom_join_url = None
        self.zoom_start_url = None
        self.teams_join_url = None
        self.status = status
        self.title = title
        self.description = None
        self.location = None
        self.external_guests = []


class FakeParticipantRow:
    def __init__(self, user_id):
        self.user_id = user_id


class AutoRescheduleTestCase(unittest.TestCase):

    def setUp(self):
        self.db = MagicMock()

        self.owner = FakeUser(id=1, email="owner@example.com")
        self.other_user = FakeUser(id=2, email="other@example.com")
        self.participant_user = FakeUser(id=3, email="participant@example.com")

        self.meetings = {}

        self.owner_busy_windows = []
        self.participant_busy_windows = []
        self.resource_busy_windows = []
        self.participant_rows = []
        self.guest_rows = []
        self.unavailable_owner_until = None
        self.unavailable_participant_until = None

        def fake_get_by_id(db, meeting_id):
            return self.meetings.get(meeting_id)

        def fake_update(db, meeting):
            return meeting

        def fake_get_meetings_between(db, owner_id, start, end):
            windows = (
                self.owner_busy_windows
                if owner_id == self.owner.id
                else self.participant_busy_windows
            )
            results = []
            for other_id, w_start, w_end in windows:
                if start < w_end and end > w_start:
                    results.append(
                        FakeMeeting(
                            id=other_id,
                            owner_id=owner_id,
                            start_time=w_start,
                            end_time=w_end,
                        )
                    )
            return results

        def fake_get_resource_bookings_between(db, resource_id, start, end):
            results = []
            for other_id, w_start, w_end in self.resource_busy_windows:
                if start < w_end and end > w_start:
                    results.append(
                        FakeMeeting(
                            id=other_id,
                            owner_id=self.owner.id,
                            start_time=w_start,
                            end_time=w_end,
                            resource_id=resource_id,
                        )
                    )
            return results

        def fake_is_user_available(db, user_id, start, end):
            if user_id == self.owner.id and self.unavailable_owner_until:
                return start >= self.unavailable_owner_until
            if (
                user_id == self.participant_user.id
                and self.unavailable_participant_until
            ):
                return start >= self.unavailable_participant_until
            return True

        def fake_participant_get_by_meeting(db, meeting_id):
            return self.participant_rows

        def fake_guest_get_by_meeting(db, meeting_id):
            return self.guest_rows

        def fake_get_users_by_ids(db, ids):
            by_id = {
                self.owner.id: self.owner,
                self.other_user.id: self.other_user,
                self.participant_user.id: self.participant_user,
            }
            return [by_id[i] for i in ids if i in by_id]

        patch_specs = [
            ("get_by_id", MeetingRepository, "get_by_id", fake_get_by_id),
            ("update", MeetingRepository, "update", fake_update),
            (
                "get_meetings_between",
                MeetingRepository,
                "get_meetings_between",
                fake_get_meetings_between,
            ),
            (
                "get_resource_bookings_between",
                MeetingRepository,
                "get_resource_bookings_between",
                fake_get_resource_bookings_between,
            ),
            (
                "participant_get_by_meeting",
                MeetingParticipantRepository,
                "get_by_meeting",
                fake_participant_get_by_meeting,
            ),
            (
                "guest_get_by_meeting",
                ExternalMeetingGuestRepository,
                "get_by_meeting",
                fake_guest_get_by_meeting,
            ),
            (
                "get_users_by_ids",
                UserRepository,
                "get_users_by_ids",
                fake_get_users_by_ids,
            ),
            (
                "is_user_available",
                AvailabilityService,
                "is_user_available",
                fake_is_user_available,
            ),
        ]

        self.mocks = {}

        for name, target, attr, side_effect in patch_specs:
            p = patch.object(target, attr, side_effect=side_effect)
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)

        extra_patches = {
            "calendar_update": patch.object(
                GoogleCalendarService,
                "update_google_calendar_event",
                return_value=None,
            ),
            "email_send": patch.object(
                EmailService,
                "send_meeting_update",
                return_value=None,
            ),
            "analytics_record": patch.object(
                AnalyticsService,
                "try_record_event",
            ),
            "participant_create_many": patch.object(
                MeetingParticipantRepository,
                "create_many",
            ),
            "participant_delete": patch.object(
                MeetingParticipantRepository,
                "delete",
            ),
            "guest_create_many": patch.object(
                ExternalMeetingGuestRepository,
                "create_many",
            ),
            "cache_delete_prefix": patch(
                "app.services.meeting_service.cache_delete_prefix",
            ),
            "cache_delete": patch(
                "app.services.meeting_service.cache_delete",
            ),
        }

        for name, p in extra_patches.items():
            self.mocks[name] = p.start()
            self.addCleanup(p.stop)

        # Spy on the real try_send_meeting_update wrapper (wraps=)
        # rather than replacing it, so its own never-raise contract
        # still runs for real - only the underlying send_meeting_update
        # (patched above) stands in for SMTP.
        email_try_patch = patch.object(
            EmailService,
            "try_send_meeting_update",
            wraps=EmailService.try_send_meeting_update,
        )
        self.mocks["email_try"] = email_try_patch.start()
        self.addCleanup(email_try_patch.stop)

    def add_meeting(self, **kwargs):
        meeting = FakeMeeting(**kwargs)
        self.meetings[meeting.id] = meeting
        return meeting

    # ------------------------------------------------------------------
    # 1. Owner can auto-reschedule
    # ------------------------------------------------------------------
    def test_owner_can_auto_reschedule_meeting_to_first_open_slot(self):
        meeting = self.add_meeting(
            id=10, owner_id=self.owner.id, google_event_id="evt-1",
        )

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 10, self.owner,
        )

        self.assertEqual(result.previous_start_time, MEETING_START)
        self.assertEqual(result.new_start_time, MEETING_START + STEP)
        self.assertEqual(result.new_end_time, MEETING_END + STEP)
        self.assertEqual(meeting.start_time, MEETING_START + STEP)
        self.assertEqual(meeting.end_time, MEETING_END + STEP)
        self.assertEqual(result.meeting.id, 10)

    # ------------------------------------------------------------------
    # 2. Non-owner is rejected
    # ------------------------------------------------------------------
    def test_non_owner_forbidden(self):
        meeting = self.add_meeting(id=11, owner_id=self.owner.id)

        with self.assertRaises(HTTPException) as ctx:
            SchedulerService.auto_reschedule_meeting(
                self.db, 11, self.other_user,
            )

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(meeting.start_time, MEETING_START)
        self.mocks["calendar_update"].assert_not_called()
        self.mocks["cache_delete_prefix"].assert_not_called()

    # ------------------------------------------------------------------
    # 3. Missing meeting returns 404
    # ------------------------------------------------------------------
    def test_missing_meeting_returns_404(self):
        with self.assertRaises(HTTPException) as ctx:
            SchedulerService.auto_reschedule_meeting(
                self.db, 999, self.owner,
            )

        self.assertEqual(ctx.exception.status_code, 404)

    # ------------------------------------------------------------------
    # 4. Duration is preserved
    # ------------------------------------------------------------------
    def test_duration_preserved(self):
        meeting = self.add_meeting(id=12, owner_id=self.owner.id)
        self.owner_busy_windows = [
            (20, MEETING_START + STEP, MEETING_END + STEP),
        ]

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 12, self.owner,
        )

        self.assertEqual(
            result.new_end_time - result.new_start_time,
            MEETING_END - MEETING_START,
        )

    # ------------------------------------------------------------------
    # 5. New slot differs from old slot
    # ------------------------------------------------------------------
    def test_new_slot_differs_from_old_slot(self):
        meeting = self.add_meeting(id=13, owner_id=self.owner.id)

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 13, self.owner,
        )

        self.assertNotEqual(
            (result.new_start_time, result.new_end_time),
            (result.previous_start_time, result.previous_end_time),
        )

    # ------------------------------------------------------------------
    # 6. Owner availability is enforced
    # ------------------------------------------------------------------
    def test_owner_availability_enforced(self):
        meeting = self.add_meeting(id=14, owner_id=self.owner.id)
        self.unavailable_owner_until = MEETING_START + STEP * 3

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 14, self.owner,
        )

        self.assertEqual(result.new_start_time, MEETING_START + STEP * 3)

    # ------------------------------------------------------------------
    # 7. Meeting conflicts are avoided (owner)
    # ------------------------------------------------------------------
    def test_owner_meeting_conflict_avoided(self):
        meeting = self.add_meeting(id=15, owner_id=self.owner.id)
        # A narrow window overlapping only the first candidate, so the
        # search should skip exactly one step and no more.
        self.owner_busy_windows = [
            (
                50,
                MEETING_START + STEP,
                MEETING_START + STEP + timedelta(minutes=1),
            ),
        ]

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 15, self.owner,
        )

        self.assertEqual(result.new_start_time, MEETING_START + STEP * 2)

    # ------------------------------------------------------------------
    # 8. Participant conflicts are avoided
    # ------------------------------------------------------------------
    def test_participant_conflict_avoided(self):
        meeting = self.add_meeting(id=16, owner_id=self.owner.id)
        self.participant_rows = [
            FakeParticipantRow(user_id=self.participant_user.id),
        ]
        self.participant_busy_windows = [
            (
                60,
                MEETING_START + STEP,
                MEETING_START + STEP + timedelta(minutes=1),
            ),
        ]

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 16, self.owner,
        )

        self.assertEqual(result.new_start_time, MEETING_START + STEP * 2)

    # ------------------------------------------------------------------
    # 9. Resource conflicts are avoided
    # ------------------------------------------------------------------
    def test_resource_conflict_avoided(self):
        meeting = self.add_meeting(
            id=17, owner_id=self.owner.id, resource_id=5,
        )
        self.resource_busy_windows = [
            (
                70,
                MEETING_START + STEP,
                MEETING_START + STEP + timedelta(minutes=1),
            ),
        ]

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 17, self.owner,
        )

        self.assertEqual(result.new_start_time, MEETING_START + STEP * 2)

    # ------------------------------------------------------------------
    # 10. Participants are preserved
    # ------------------------------------------------------------------
    def test_participants_preserved(self):
        meeting = self.add_meeting(id=18, owner_id=self.owner.id)
        self.participant_rows = [
            FakeParticipantRow(user_id=self.participant_user.id),
        ]

        SchedulerService.auto_reschedule_meeting(self.db, 18, self.owner)

        self.mocks["participant_create_many"].assert_not_called()
        self.mocks["participant_delete"].assert_not_called()

    # ------------------------------------------------------------------
    # 11. External guests are preserved
    # ------------------------------------------------------------------
    def test_external_guests_preserved(self):
        meeting = self.add_meeting(id=19, owner_id=self.owner.id)
        self.guest_rows = [MagicMock(email="guest@example.com")]

        SchedulerService.auto_reschedule_meeting(self.db, 19, self.owner)

        self.mocks["guest_create_many"].assert_not_called()

    # ------------------------------------------------------------------
    # 12. Resource assignment is preserved when valid
    # ------------------------------------------------------------------
    def test_resource_assignment_preserved_when_valid(self):
        meeting = self.add_meeting(
            id=20, owner_id=self.owner.id, resource_id=7,
        )

        SchedulerService.auto_reschedule_meeting(self.db, 20, self.owner)

        self.assertEqual(meeting.resource_id, 7)

    # ------------------------------------------------------------------
    # 13. No valid slot -> clear 4xx and meeting unchanged
    # ------------------------------------------------------------------
    def test_no_valid_slot_returns_404_and_meeting_unchanged(self):
        meeting = self.add_meeting(id=21, owner_id=self.owner.id)
        self.unavailable_owner_until = MEETING_START + timedelta(days=30)

        with self.assertRaises(HTTPException) as ctx:
            SchedulerService.auto_reschedule_meeting(
                self.db, 21, self.owner,
            )

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(meeting.start_time, MEETING_START)
        self.assertEqual(meeting.end_time, MEETING_END)
        self.mocks["calendar_update"].assert_not_called()
        self.mocks["email_try"].assert_not_called()
        self.mocks["cache_delete_prefix"].assert_not_called()

    # ------------------------------------------------------------------
    # 14. Successful reschedule updates the existing row, no duplicate
    # ------------------------------------------------------------------
    def test_successful_reschedule_updates_existing_row_no_duplicate(self):
        meeting = self.add_meeting(id=22, owner_id=self.owner.id)

        with patch.object(MeetingRepository, "create") as create_mock:
            SchedulerService.auto_reschedule_meeting(
                self.db, 22, self.owner,
            )
            create_mock.assert_not_called()

        self.assertEqual(len(self.meetings), 1)
        self.mocks["update"].assert_called_once()

    # ------------------------------------------------------------------
    # 15. Google Calendar update attempted exactly once
    # ------------------------------------------------------------------
    def test_google_calendar_update_attempted_exactly_once(self):
        meeting = self.add_meeting(
            id=23, owner_id=self.owner.id, google_event_id="evt-23",
        )

        SchedulerService.auto_reschedule_meeting(self.db, 23, self.owner)

        self.mocks["calendar_update"].assert_called_once()

    def test_google_calendar_not_called_when_no_event_id(self):
        meeting = self.add_meeting(
            id=24, owner_id=self.owner.id, google_event_id=None,
        )

        SchedulerService.auto_reschedule_meeting(self.db, 24, self.owner)

        self.mocks["calendar_update"].assert_not_called()

    # ------------------------------------------------------------------
    # 16. Emails attempted exactly once per unique recipient
    # ------------------------------------------------------------------
    def test_emails_attempted_exactly_once_per_unique_recipient(self):
        meeting = self.add_meeting(id=25, owner_id=self.owner.id)
        self.participant_rows = [
            FakeParticipantRow(user_id=self.participant_user.id),
        ]
        # Same address as the participant, different case - must be
        # deduped down to a single send.
        self.guest_rows = [MagicMock(email="Participant@Example.com")]

        SchedulerService.auto_reschedule_meeting(self.db, 25, self.owner)

        self.mocks["email_try"].assert_called_once()
        self.assertEqual(
            self.mocks["email_try"].call_args.kwargs["to_email"],
            "participant@example.com",
        )

    # ------------------------------------------------------------------
    # 17. Redis meeting caches invalidated
    # ------------------------------------------------------------------
    def test_redis_meeting_cache_invalidated(self):
        from app.core.cache import meetings_list_prefix

        meeting = self.add_meeting(id=26, owner_id=self.owner.id)

        SchedulerService.auto_reschedule_meeting(self.db, 26, self.owner)

        self.mocks["cache_delete_prefix"].assert_called_once()
        self.assertEqual(
            self.mocks["cache_delete_prefix"].call_args.args[0],
            meetings_list_prefix(self.owner.id),
        )

    # ------------------------------------------------------------------
    # 18. No invented/misleading KPI event
    # ------------------------------------------------------------------
    def test_no_new_kpi_event_recorded(self):
        meeting = self.add_meeting(id=27, owner_id=self.owner.id)

        SchedulerService.auto_reschedule_meeting(self.db, 27, self.owner)

        self.mocks["analytics_record"].assert_not_called()

    # ------------------------------------------------------------------
    # 19. Calendar failure isolated
    # ------------------------------------------------------------------
    def test_calendar_failure_isolated(self):
        meeting = self.add_meeting(
            id=28, owner_id=self.owner.id, google_event_id="evt-28",
        )
        self.mocks["calendar_update"].side_effect = Exception(
            "Calendar API down"
        )

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 28, self.owner,
        )

        self.assertEqual(meeting.start_time, result.new_start_time)
        self.mocks["calendar_update"].assert_called_once()

    # ------------------------------------------------------------------
    # 20. SMTP failure isolated
    # ------------------------------------------------------------------
    def test_smtp_failure_isolated(self):
        meeting = self.add_meeting(id=29, owner_id=self.owner.id)
        self.participant_rows = [
            FakeParticipantRow(user_id=self.participant_user.id),
        ]
        self.mocks["email_send"].side_effect = Exception("SMTP down")

        result = SchedulerService.auto_reschedule_meeting(
            self.db, 29, self.owner,
        )

        self.assertEqual(meeting.start_time, result.new_start_time)
        self.mocks["email_try"].assert_called_once()

    # ------------------------------------------------------------------
    # 21. Redis failure isolated
    # ------------------------------------------------------------------
    def test_redis_failure_isolated(self):
        from app.core.cache import cache_delete_prefix as real_cache_delete_prefix

        meeting = self.add_meeting(id=30, owner_id=self.owner.id)

        broken_client = MagicMock()
        broken_client.scan_iter.side_effect = Exception("redis down")

        with patch(
            "app.core.cache._get_client", return_value=broken_client,
        ), patch(
            "app.services.meeting_service.cache_delete_prefix",
            side_effect=real_cache_delete_prefix,
        ):
            result = SchedulerService.auto_reschedule_meeting(
                self.db, 30, self.owner,
            )

        self.assertEqual(meeting.start_time, result.new_start_time)

    # ------------------------------------------------------------------
    # 22. Recurring-meeting behavior: only the targeted row is touched
    # ------------------------------------------------------------------
    def test_recurring_series_only_targeted_occurrence_is_touched(self):
        occurrence_1 = self.add_meeting(
            id=31,
            owner_id=self.owner.id,
            start_time=MEETING_START,
            end_time=MEETING_END,
        )
        occurrence_2 = self.add_meeting(
            id=32,
            owner_id=self.owner.id,
            start_time=MEETING_START + timedelta(days=7),
            end_time=MEETING_END + timedelta(days=7),
        )

        SchedulerService.auto_reschedule_meeting(self.db, 31, self.owner)

        self.assertNotEqual(occurrence_1.start_time, MEETING_START)
        self.assertEqual(
            occurrence_2.start_time, MEETING_START + timedelta(days=7),
        )


if __name__ == "__main__":
    unittest.main()
