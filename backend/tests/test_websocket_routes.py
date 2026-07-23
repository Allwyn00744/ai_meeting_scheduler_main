"""
Integration tests for the WebSocket subsystem (app/websocket
/connection_manager.py, app/api/websocket_routes.py) and its
broadcast hooks in MeetingService.create_meeting/update_meeting
/delete_meeting.

Uses `with TestClient(app) as client:` (not the bare constructor used
elsewhere in this suite) specifically because only the context-manager
form triggers FastAPI's lifespan startup/shutdown - required here
since the event loop connection_manager broadcasts onto is captured
inside that lifespan (see app/main.py).

Run with: python -m unittest tests.test_websocket_routes -v
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

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402

MEETING_START = datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
MEETING_END = MEETING_START + timedelta(hours=1)


class WebSocketRoutesTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.addCleanup(app.dependency_overrides.clear)
        self.addCleanup(self.engine.dispose)

    def _register_and_login(self, email="owner@example.com"):
        with TestClient(app) as client:
            register_resp = client.post(
                "/auth/register",
                json={
                    "name": "Owner",
                    "email": email,
                    "password": "correct horse battery staple",
                    "timezone": "UTC",
                },
            )
            self.assertEqual(register_resp.status_code, 201)
            login_resp = client.post(
                "/auth/login",
                json={"email": email, "password": "correct horse battery staple"},
            )
            self.assertEqual(login_resp.status_code, 200)
            return login_resp.json()["access_token"]

    def test_connection_without_token_is_rejected(self):
        with TestClient(app) as client:
            with self.assertRaises(Exception):
                with client.websocket_connect("/ws"):
                    pass

    def test_connection_with_invalid_token_is_rejected(self):
        with TestClient(app) as client:
            with self.assertRaises(Exception):
                with client.websocket_connect("/ws?token=not-a-real-token"):
                    pass

    def test_meeting_created_broadcasts_to_owning_users_socket(self):
        token = self._register_and_login()

        with TestClient(app) as client:
            with client.websocket_connect(f"/ws?token={token}") as ws:
                create_resp = client.post(
                    "/meetings/",
                    json={
                        "title": "Sync",
                        "start_time": MEETING_START.isoformat(),
                        "end_time": MEETING_END.isoformat(),
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(create_resp.status_code, 201, create_resp.text)
                meeting_id = create_resp.json()["id"]

                message = ws.receive_json()

        self.assertEqual(message["type"], "meeting_created")
        self.assertEqual(message["meeting_id"], meeting_id)

    def test_cancelling_a_meeting_broadcasts_meeting_cancelled(self):
        token = self._register_and_login("owner2@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        with TestClient(app) as client:
            create_resp = client.post(
                "/meetings/",
                json={
                    "title": "Sync",
                    "start_time": MEETING_START.isoformat(),
                    "end_time": MEETING_END.isoformat(),
                },
                headers=headers,
            )
            meeting_id = create_resp.json()["id"]

            with client.websocket_connect(f"/ws?token={token}") as ws:
                delete_resp = client.delete(
                    f"/meetings/{meeting_id}",
                    headers=headers,
                )
                self.assertEqual(delete_resp.status_code, 200)

                message = ws.receive_json()

        self.assertEqual(message["type"], "meeting_cancelled")
        self.assertEqual(message["meeting_id"], meeting_id)


if __name__ == "__main__":
    unittest.main()
