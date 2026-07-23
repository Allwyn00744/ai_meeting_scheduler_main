"""
Integration tests for Slack Notifications' OAuth surface: POST
/slack/connect, GET /slack/callback, GET /slack/status, and DELETE
/slack/disconnect. Mirrors the style of tests/test_zoom_oauth.py: a
real FastAPI app via starlette's TestClient, backed by an in-memory
SQLite DB.

Network calls to Slack (oauth.v2.access token exchange) are mocked at
the SlackOAuthService boundary - everything else (state generation/
consumption, credential persistence, routing) runs for real.

Run with: python -m unittest tests.test_slack_oauth -v
(from the backend/ directory)
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


FAKE_TOKEN_RESPONSE = {
    "ok": True,
    "access_token": "xoxb-fake-bot-token",
    "token_type": "bot",
    "scope": "chat:write",
    "bot_user_id": "UBOT123",
    "app_id": "A123",
    "team": {"id": "T123", "name": "Fake Team"},
    "authed_user": {"id": "U123", "scope": "", "access_token": None, "token_type": None},
}


class SlackOAuthTestCase(unittest.TestCase):

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

        # Slack OAuth is optional/unconfigured by default (see
        # core/config.py) - give tests a configured pair and restore
        # the original values afterwards, since `settings` is a
        # process-wide singleton shared with every other test module.
        self._orig_client_id = settings.SLACK_CLIENT_ID
        self._orig_client_secret = settings.SLACK_CLIENT_SECRET
        settings.SLACK_CLIENT_ID = "test-client-id"
        settings.SLACK_CLIENT_SECRET = "test-client-secret"

        def _restore_settings():
            settings.SLACK_CLIENT_ID = self._orig_client_id
            settings.SLACK_CLIENT_SECRET = self._orig_client_secret

        self.addCleanup(_restore_settings)

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

    def test_status_not_connected_by_default(self):
        response = self.client.get("/slack/status", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connected": False})

    def test_connect_requires_auth(self):
        response = self.client.post("/slack/connect")
        self.assertEqual(response.status_code, 401)

    def test_connect_returns_authorization_url(self):
        response = self.client.post("/slack/connect", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("authorization_url", body)
        self.assertTrue(
            body["authorization_url"].startswith(
                "https://slack.com/oauth/v2/authorize"
            )
        )

    def test_connect_returns_503_when_not_configured(self):
        settings.SLACK_CLIENT_ID = None
        settings.SLACK_CLIENT_SECRET = None

        response = self.client.post("/slack/connect", headers=self.auth_headers)
        self.assertEqual(response.status_code, 503)

    def test_callback_missing_state_redirects_to_error(self):
        response = self.client.get("/slack/callback", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertIn("slack=error", response.headers["location"])

    def test_callback_invalid_state_redirects_to_error(self):
        response = self.client.get(
            "/slack/callback",
            params={"state": "bogus-state", "code": "some-code"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("slack=error", response.headers["location"])

    def test_callback_success_persists_credential_and_status_reflects_it(self):
        connect_resp = self.client.post(
            "/slack/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.slack_routes.SlackOAuthService.exchange_code_for_token",
            return_value=FAKE_TOKEN_RESPONSE,
        ):
            callback_resp = self.client.get(
                "/slack/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        self.assertEqual(callback_resp.status_code, 307)
        self.assertIn("slack=connected", callback_resp.headers["location"])

        status_resp = self.client.get("/slack/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": True})

    def test_callback_token_exchange_error_redirects_to_error(self):
        connect_resp = self.client.post(
            "/slack/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.slack_routes.SlackOAuthService.exchange_code_for_token",
            return_value={"ok": False, "error": "invalid_code"},
        ):
            callback_resp = self.client.get(
                "/slack/callback",
                params={"state": state, "code": "bad-code"},
                follow_redirects=False,
            )

        self.assertEqual(callback_resp.status_code, 307)
        self.assertIn("slack=error", callback_resp.headers["location"])

        status_resp = self.client.get("/slack/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": False})

    def test_state_is_single_use(self):
        connect_resp = self.client.post(
            "/slack/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.slack_routes.SlackOAuthService.exchange_code_for_token",
            return_value=FAKE_TOKEN_RESPONSE,
        ):
            first = self.client.get(
                "/slack/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )
            second = self.client.get(
                "/slack/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        self.assertIn("slack=connected", first.headers["location"])
        self.assertIn("slack=error", second.headers["location"])

    def test_disconnect_when_not_connected_returns_404(self):
        response = self.client.delete(
            "/slack/disconnect",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_disconnect_removes_credential(self):
        connect_resp = self.client.post(
            "/slack/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.slack_routes.SlackOAuthService.exchange_code_for_token",
            return_value=FAKE_TOKEN_RESPONSE,
        ):
            self.client.get(
                "/slack/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        disconnect_resp = self.client.delete(
            "/slack/disconnect",
            headers=self.auth_headers,
        )
        self.assertEqual(disconnect_resp.status_code, 200)

        status_resp = self.client.get("/slack/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": False})


if __name__ == "__main__":
    unittest.main()
