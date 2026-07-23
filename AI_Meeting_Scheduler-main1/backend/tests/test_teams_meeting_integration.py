"""
Integration tests for Microsoft Teams meeting sync: the automatic
best-effort hook in MeetingService.create_meeting (which only runs
after the Outlook block in that same method has already created an
Outlook event), and the manual POST/PUT/DELETE
/teams/sync/{meeting_id} endpoints. Mirrors the style of
tests/test_outlook_calendar_integration.py and
tests/test_zoom_meeting_integration.py: a real FastAPI app via
starlette's TestClient, backed by an in-memory SQLite DB.

Microsoft Graph calls are mocked at two boundaries:
- OutlookCalendarAPI.create_calendar_event (to produce an
  outlook_event_id for Teams to extend)
- TeamsMeetingAPI.enable_teams_meeting / disable_teams_meeting (the
  actual Teams-specific Graph calls)

There is deliberately no test file for a Teams OAuth flow, and no
/teams/connect, /teams/callback, or /teams/disconnect endpoints exist -
Teams Integration V1 reuses the existing OutlookCredential row and
MicrosoftOAuthService token refresh, both already covered by
test_outlook_oauth.py and test_outlook_calendar_integration.py.

Run with: python -m unittest tests.test_teams_meeting_integration -v
(from the backend/ directory)
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.meeting import Meeting  # noqa: E402
from app.models.outlook_credential import OutlookCredential  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

FAKE_OUTLOOK_EVENT = {
    "id": "graph-event-1",
    "webLink": "https://outlook.office.com/event-1",
}

FAKE_TEAMS_EVENT = {
    "id": "graph-event-1",
    "webLink": "https://outlook.office.com/event-1",
    "onlineMeeting": {
        "joinUrl": "https://teams.microsoft.com/l/meetup-join/abc123",
    },
}

FAKE_TEAMS_EVENT_UPDATED = {
    "id": "graph-event-1",
    "onlineMeeting": {
        "joinUrl": "https://teams.microsoft.com/l/meetup-join/xyz789",
    },
}


def _forbidden_error() -> requests.exceptions.RequestException:
    response = requests.Response()
    response.status_code = 403
    return requests.exceptions.HTTPError(response=response)


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class TeamsMeetingIntegrationTestCase(unittest.TestCase):

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

        other_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Other",
                "email": "other@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(other_resp.status_code, 201)

        other_login = self.client.post(
            "/auth/login",
            json={
                "email": "other@example.com",
                "password": "correct horse battery staple",
            },
        )
        other_token = other_login.json()["access_token"]
        self.other_auth_headers = {"Authorization": f"Bearer {other_token}"}

    def _create_meeting(self):
        resp = self.client.post(
            "/meetings/",
            json={
                "title": "Sync",
                "start_time": MEETING_START.isoformat(),
                "end_time": MEETING_END.isoformat(),
            },
            headers=self.auth_headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.json()["id"]

    def _connect_outlook(self, user_id: int | None = None):
        """Directly persists an OutlookCredential row, bypassing the
        OAuth flow itself - that flow is covered by
        test_outlook_oauth.py. Teams Integration V1 reuses this same
        row; there is no separate Teams credential."""
        db = self.SessionLocal()
        try:
            db.add(
                OutlookCredential(
                    user_id=user_id or self.owner_id,
                    access_token="fake-access-token",
                    refresh_token="fake-refresh-token",
                    scopes="Calendars.ReadWrite OnlineMeetings.ReadWrite",
                    expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            db.commit()
        finally:
            db.close()

    def _sync_outlook(self, meeting_id):
        with patch(
            "app.services.outlook_calendar_service.OutlookCalendarAPI.create_calendar_event",
            return_value=FAKE_OUTLOOK_EVENT,
        ):
            resp = self.client.post(
                f"/outlook/sync/{meeting_id}",
                headers=self.auth_headers,
            )
        self.assertEqual(resp.status_code, 200)

    # ---- GET /teams/status ----

    def test_status_reflects_outlook_connection(self):
        not_connected = self.client.get(
            "/teams/status",
            headers=self.auth_headers,
        )
        self.assertEqual(not_connected.json(), {"connected": False})

        self._connect_outlook()

        connected = self.client.get(
            "/teams/status",
            headers=self.auth_headers,
        )
        self.assertEqual(connected.json(), {"connected": True})

    # ---- automatic sync hook (MeetingService.create_meeting) ----

    def test_create_meeting_skips_gracefully_when_outlook_not_connected(self):
        meeting_id = self._create_meeting()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertIsNone(get_resp.json()["teams_join_url"])

    def test_create_meeting_auto_syncs_when_outlook_connected(self):
        self._connect_outlook()

        with patch(
            "app.services.outlook_calendar_service.OutlookCalendarAPI.create_calendar_event",
            return_value=FAKE_OUTLOOK_EVENT,
        ), patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ) as mock_enable:
            meeting_id = self._create_meeting()

        mock_enable.assert_called_once()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(
            get_resp.json()["teams_join_url"],
            "https://teams.microsoft.com/l/meetup-join/abc123",
        )

        # Already synced by the automatic hook above.
        sync_resp = self.client.post(
            f"/teams/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(sync_resp.status_code, 409)

    def test_create_meeting_auto_sync_skipped_when_outlook_event_missing(self):
        """Teams never creates its own Outlook event - if the Outlook
        block failed (or Outlook isn't connected), Teams sync must not
        run at all."""
        self._connect_outlook()

        with patch(
            "app.services.outlook_calendar_service.OutlookCalendarAPI.create_calendar_event",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ), patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
        ) as mock_enable:
            self._create_meeting()

        mock_enable.assert_not_called()

    # ---- manual sync: create ----

    def test_manual_sync_create_requires_prior_outlook_sync(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/teams/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_sync_create_requires_outlook_connected(self):
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/teams/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_sync_create_success(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ):
            response = self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["teams_join_url"],
            "https://teams.microsoft.com/l/meetup-join/abc123",
        )

    def test_manual_sync_create_duplicate_returns_409(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ):
            first = self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )
            second = self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_manual_sync_create_meeting_not_found(self):
        response = self.client.post(
            "/teams/sync/999999",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_sync_create_unauthorized_wrong_owner(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        response = self.client.post(
            f"/teams/sync/{meeting_id}",
            headers=self.other_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_manual_sync_create_no_token_unauthorized(self):
        meeting_id = self._create_meeting()
        response = self.client.post(f"/teams/sync/{meeting_id}")
        self.assertEqual(response.status_code, 401)

    def test_manual_sync_create_graph_unavailable_returns_502(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            response = self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 502)

    def test_manual_sync_create_insufficient_scope_asks_to_reconnect(self):
        """A token that predates OnlineMeetings.ReadWrite surfaces as
        a Graph 403 - this must come back as a friendly, actionable
        400 rather than a bare 502, per architecture decision 8."""
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            side_effect=_forbidden_error(),
        ):
            response = self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("reconnect", response.json()["detail"].lower())

    # ---- manual sync: update ----

    def test_manual_sync_update_requires_prior_sync(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        response = self.client.put(
            f"/teams/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_sync_update_success(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ):
            self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT_UPDATED,
        ) as mock_update:
            response = self.client.put(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once()
        self.assertEqual(
            response.json()["teams_join_url"],
            "https://teams.microsoft.com/l/meetup-join/xyz789",
        )

    # ---- manual sync: delete ----

    def test_manual_sync_delete_when_never_synced_is_a_noop(self):
        meeting_id = self._create_meeting()

        response = self.client.delete(
            f"/teams/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("not synced", response.json()["message"])

    def test_manual_sync_delete_unlinks_without_deleting_outlook_event(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ):
            self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.disable_teams_meeting",
            return_value={"id": "graph-event-1"},
        ) as mock_disable, patch(
            "app.services.outlook_calendar_service.OutlookCalendarAPI.delete_calendar_event",
        ) as mock_outlook_delete:
            response = self.client.delete(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_disable.assert_called_once()
        # Unlinking Teams must never touch the Outlook event itself.
        mock_outlook_delete.assert_not_called()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertIsNone(get_resp.json()["teams_join_url"])

    # ---- meeting delete (Teams needs no separate cleanup call) ----

    def test_meeting_delete_succeeds_with_teams_synced(self):
        self._connect_outlook()
        meeting_id = self._create_meeting()
        self._sync_outlook(meeting_id)

        with patch(
            "app.services.teams_meeting_service.TeamsMeetingAPI.enable_teams_meeting",
            return_value=FAKE_TEAMS_EVENT,
        ):
            self.client.post(
                f"/teams/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.outlook_calendar_service.OutlookCalendarAPI.delete_calendar_event",
            return_value=True,
        ) as mock_outlook_delete:
            response = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        # Deleting the Outlook event is enough - no separate Teams API
        # call exists for meeting deletion.
        mock_outlook_delete.assert_called_once()


if __name__ == "__main__":
    unittest.main()
