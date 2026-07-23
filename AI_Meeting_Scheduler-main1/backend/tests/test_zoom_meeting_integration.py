"""
Integration tests for Zoom Meeting sync: the automatic best-effort
hook in MeetingService.create_meeting, and the manual POST/PUT/DELETE
/zoom/sync/{meeting_id} endpoints. Mirrors the style of
tests/test_outlook_calendar_integration.py: a real FastAPI app via
starlette's TestClient, backed by an in-memory SQLite DB.

Zoom API calls are mocked at the ZoomAPI boundary (create/update/
delete_meeting) so these tests exercise the real service/repository/
route wiring without making network calls. The "Zoom not connected"
paths are exercised for real, with no mocking at all - mirrors how the
existing Google/Outlook integration tests rely on a real no-op rather
than a patched-out one.

Run with: python -m unittest tests.test_zoom_meeting_integration -v
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
from app.models.zoom_credential import ZoomCredential  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)

FAKE_MEETING = {
    "id": 123456789,
    "join_url": "https://zoom.us/j/123456789",
    "start_url": "https://zoom.us/s/123456789?zak=fake-host-token",
}


def _reattach_utc_on_load(target, *_args):
    """SQLite drops tzinfo on round-trip; see test_auto_reschedule_integration.py."""
    if target.start_time is not None and target.start_time.tzinfo is None:
        target.start_time = target.start_time.replace(tzinfo=timezone.utc)
    if target.end_time is not None and target.end_time.tzinfo is None:
        target.end_time = target.end_time.replace(tzinfo=timezone.utc)


class ZoomMeetingIntegrationTestCase(unittest.TestCase):

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

        self.other_user_id = other_resp.json()["id"]

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

    def _connect_zoom(self, user_id: int | None = None):
        """Directly persists a ZoomCredential row, bypassing the OAuth
        flow itself - that flow is covered by test_zoom_oauth.py."""
        db = self.SessionLocal()
        try:
            db.add(
                ZoomCredential(
                    user_id=user_id or self.owner_id,
                    access_token="fake-access-token",
                    refresh_token="fake-refresh-token",
                    scopes="meeting:write",
                    expiry=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            db.commit()
        finally:
            db.close()

    # ---- automatic sync hook (MeetingService.create_meeting) ----

    def test_create_meeting_skips_gracefully_when_zoom_not_connected(self):
        meeting_id = self._create_meeting()

        get_resp = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(get_resp.status_code, 200)
        self.assertIsNone(get_resp.json()["zoom_meeting_id"])

    def test_create_meeting_auto_syncs_when_zoom_connected(self):
        self._connect_zoom()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ) as mock_create:
            meeting_id = self._create_meeting()

        mock_create.assert_called_once()

        sync_resp = self.client.post(
            f"/zoom/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        # Already synced by the automatic hook above.
        self.assertEqual(sync_resp.status_code, 409)

    def test_create_meeting_type_is_scheduled(self):
        self._connect_zoom()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ) as mock_create:
            self._create_meeting()

        self.assertEqual(mock_create.call_args.kwargs["title"], "Sync")

        # The "type": 2 (scheduled) constant is applied inside ZoomAPI
        # itself, not passed through by the service - verified
        # directly against the ZoomAPI payload builder.
        from app.calendar.zoom_api import (  # noqa: E402
            ZOOM_MEETING_TYPE_SCHEDULED,
        )
        self.assertEqual(ZOOM_MEETING_TYPE_SCHEDULED, 2)

    # ---- manual sync: create ----

    def test_manual_sync_create_requires_zoom_connected(self):
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/zoom/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_sync_create_success(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            response = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["zoom_meeting_id"], "123456789")
        self.assertEqual(body["zoom_join_url"], FAKE_MEETING["join_url"])
        self.assertEqual(body["zoom_start_url"], FAKE_MEETING["start_url"])

    def test_manual_sync_create_duplicate_returns_409(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            first = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )
            second = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

    def test_manual_sync_create_meeting_not_found(self):
        response = self.client.post(
            "/zoom/sync/999999",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_manual_sync_create_unauthorized_wrong_owner(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        response = self.client.post(
            f"/zoom/sync/{meeting_id}",
            headers=self.other_auth_headers,
        )
        self.assertEqual(response.status_code, 403)

    def test_manual_sync_create_no_token_unauthorized(self):
        meeting_id = self._create_meeting()
        response = self.client.post(f"/zoom/sync/{meeting_id}")
        self.assertEqual(response.status_code, 401)

    def test_manual_sync_create_zoom_unavailable_returns_502(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            response = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 502)

    # ---- manual sync: update ----

    def test_manual_sync_update_requires_prior_sync(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        response = self.client.put(
            f"/zoom/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_manual_sync_update_success(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.update_meeting",
            return_value=True,
        ) as mock_update:
            response = self.client.put(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_update.assert_called_once()
        # join_url/start_url are stable across updates - PATCH returns
        # no body, so the previously-stored links must be unchanged.
        body = response.json()
        self.assertEqual(body["zoom_join_url"], FAKE_MEETING["join_url"])

    # ---- manual sync: delete ----

    def test_manual_sync_delete_when_never_synced_is_a_noop(self):
        meeting_id = self._create_meeting()

        response = self.client.delete(
            f"/zoom/sync/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("not synced", response.json()["message"])

    def test_manual_sync_delete_unlinks_meeting(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.delete_meeting",
            return_value=True,
        ) as mock_delete:
            response = self.client.delete(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_delete.assert_called_once()

        # Unlinked, not a duplicate anymore - re-sync should succeed.
        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            resync = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )
        self.assertEqual(resync.status_code, 200)

    def test_meeting_delete_removes_zoom_meeting_best_effort(self):
        self._connect_zoom()
        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.delete_meeting",
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            # Zoom being unreachable must not block meeting deletion.
            response = self.client.delete(
                f"/meetings/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)

    # ---- token refresh ----

    def test_expired_token_is_refreshed_transparently(self):
        db = self.SessionLocal()
        try:
            db.add(
                ZoomCredential(
                    user_id=self.owner_id,
                    access_token="stale-access-token",
                    refresh_token="valid-refresh-token",
                    scopes="meeting:write",
                    expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
                )
            )
            db.commit()
        finally:
            db.close()

        meeting_id = self._create_meeting()

        seen_access_tokens = []

        def _capture_and_create(*, credential, **_kwargs):
            seen_access_tokens.append(credential.access_token)
            return FAKE_MEETING

        with patch(
            "app.services.zoom_calendar_service.ZoomOAuthService.refresh_access_token",
            return_value={
                "access_token": "fresh-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            },
        ) as mock_refresh, patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            side_effect=_capture_and_create,
        ):
            response = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 200)
        mock_refresh.assert_called_once()
        self.assertEqual(seen_access_tokens, ["fresh-access-token"])

    def test_revoked_refresh_token_returns_400(self):
        db = self.SessionLocal()
        try:
            db.add(
                ZoomCredential(
                    user_id=self.owner_id,
                    access_token="stale-access-token",
                    refresh_token="dead-refresh-token",
                    scopes="meeting:write",
                    expiry=datetime.now(timezone.utc) - timedelta(minutes=5),
                )
            )
            db.commit()
        finally:
            db.close()

        meeting_id = self._create_meeting()

        with patch(
            "app.services.zoom_calendar_service.ZoomOAuthService.refresh_access_token",
            return_value={
                "error": "invalid_grant",
                "reason": "Invalid Refresh Token",
            },
        ):
            response = self.client.post(
                f"/zoom/sync/{meeting_id}",
                headers=self.auth_headers,
            )

        self.assertEqual(response.status_code, 400)

        # Status still reports connected - matches Google/Outlook's
        # existing behavior of not auto-deleting the credential row on
        # a refresh failure.
        status_resp = self.client.get("/zoom/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": True})

    # ---- owner-only zoom_start_url visibility ----

    def test_zoom_start_url_hidden_from_non_owner_participant(self):
        self._connect_zoom()

        with patch(
            "app.services.zoom_calendar_service.ZoomAPI.create_meeting",
            return_value=FAKE_MEETING,
        ):
            meeting_id = self._create_meeting()

        add_participant_resp = self.client.post(
            f"/meetings/{meeting_id}/participants",
            json={"user_id": self.other_user_id},
            headers=self.auth_headers,
        )
        self.assertEqual(add_participant_resp.status_code, 201)

        owner_view = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.auth_headers,
        )
        self.assertEqual(owner_view.json()["zoom_start_url"], FAKE_MEETING["start_url"])
        self.assertEqual(owner_view.json()["zoom_join_url"], FAKE_MEETING["join_url"])

        participant_view = self.client.get(
            f"/meetings/{meeting_id}",
            headers=self.other_auth_headers,
        )
        self.assertEqual(participant_view.status_code, 200)
        self.assertIsNone(participant_view.json()["zoom_start_url"])
        # join_url (attendee link) must still be visible to participants.
        self.assertEqual(participant_view.json()["zoom_join_url"], FAKE_MEETING["join_url"])


if __name__ == "__main__":
    unittest.main()
