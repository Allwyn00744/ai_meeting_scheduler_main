"""
Integration tests for Zoom Meeting's OAuth surface: POST /zoom/connect,
GET /zoom/callback, GET /zoom/status, and DELETE /zoom/disconnect.
Mirrors the style of tests/test_outlook_oauth.py: a real FastAPI app
via starlette's TestClient, backed by an in-memory SQLite DB.

Network calls to Zoom (token exchange, token refresh) are mocked at
the ZoomOAuthService boundary - everything else (state generation/
consumption, credential persistence, routing) runs for real.

Run with: python -m unittest tests.test_zoom_oauth -v
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


class ZoomOAuthTestCase(unittest.TestCase):

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

        # Zoom OAuth is optional/unconfigured by default (see
        # core/config.py) - give tests a configured pair and restore
        # the original values afterwards, since `settings` is a
        # process-wide singleton shared with every other test module.
        self._orig_client_id = settings.ZOOM_CLIENT_ID
        self._orig_client_secret = settings.ZOOM_CLIENT_SECRET
        settings.ZOOM_CLIENT_ID = "test-client-id"
        settings.ZOOM_CLIENT_SECRET = "test-client-secret"

        def _restore_settings():
            settings.ZOOM_CLIENT_ID = self._orig_client_id
            settings.ZOOM_CLIENT_SECRET = self._orig_client_secret

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
        response = self.client.get("/zoom/status", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"connected": False})

    def test_connect_requires_auth(self):
        response = self.client.post("/zoom/connect")
        self.assertEqual(response.status_code, 401)

    def test_connect_returns_authorization_url(self):
        response = self.client.post("/zoom/connect", headers=self.auth_headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("authorization_url", body)
        self.assertTrue(
            body["authorization_url"].startswith(
                "https://zoom.us/oauth/authorize"
            )
        )

    def test_connect_returns_503_when_not_configured(self):
        settings.ZOOM_CLIENT_ID = None
        settings.ZOOM_CLIENT_SECRET = None

        response = self.client.post("/zoom/connect", headers=self.auth_headers)
        self.assertEqual(response.status_code, 503)

    def test_callback_missing_state_redirects_to_error(self):
        response = self.client.get("/zoom/callback", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertIn("zoom=error", response.headers["location"])

    def test_callback_invalid_state_redirects_to_error(self):
        response = self.client.get(
            "/zoom/callback",
            params={"state": "bogus-state", "code": "some-code"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 307)
        self.assertIn("zoom=error", response.headers["location"])

    def test_callback_success_persists_credential_and_status_reflects_it(self):
        connect_resp = self.client.post(
            "/zoom/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        fake_token_response = {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "expires_in": 3600,
            "scope": "meeting:write",
        }

        with patch(
            "app.api.zoom_routes.ZoomOAuthService.exchange_code_for_token",
            return_value=fake_token_response,
        ):
            callback_resp = self.client.get(
                "/zoom/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        self.assertEqual(callback_resp.status_code, 307)
        self.assertIn("zoom=connected", callback_resp.headers["location"])

        status_resp = self.client.get("/zoom/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": True})

    def test_callback_token_exchange_error_redirects_to_error(self):
        connect_resp = self.client.post(
            "/zoom/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.zoom_routes.ZoomOAuthService.exchange_code_for_token",
            return_value={"error": "invalid_grant"},
        ):
            callback_resp = self.client.get(
                "/zoom/callback",
                params={"state": state, "code": "bad-code"},
                follow_redirects=False,
            )

        self.assertEqual(callback_resp.status_code, 307)
        self.assertIn("zoom=error", callback_resp.headers["location"])

        status_resp = self.client.get("/zoom/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": False})

    def test_state_is_single_use(self):
        connect_resp = self.client.post(
            "/zoom/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        fake_token_response = {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "expires_in": 3600,
            "scope": "meeting:write",
        }

        with patch(
            "app.api.zoom_routes.ZoomOAuthService.exchange_code_for_token",
            return_value=fake_token_response,
        ):
            first = self.client.get(
                "/zoom/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )
            second = self.client.get(
                "/zoom/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        self.assertIn("zoom=connected", first.headers["location"])
        self.assertIn("zoom=error", second.headers["location"])

    def test_disconnect_when_not_connected_returns_404(self):
        response = self.client.delete(
            "/zoom/disconnect",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 404)

    def test_disconnect_removes_credential(self):
        connect_resp = self.client.post(
            "/zoom/connect",
            headers=self.auth_headers,
        )
        authorization_url = connect_resp.json()["authorization_url"]
        state = authorization_url.split("state=")[1].split("&")[0]

        with patch(
            "app.api.zoom_routes.ZoomOAuthService.exchange_code_for_token",
            return_value={
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token",
                "expires_in": 3600,
                "scope": "meeting:write",
            },
        ):
            self.client.get(
                "/zoom/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )

        disconnect_resp = self.client.delete(
            "/zoom/disconnect",
            headers=self.auth_headers,
        )
        self.assertEqual(disconnect_resp.status_code, 200)

        status_resp = self.client.get("/zoom/status", headers=self.auth_headers)
        self.assertEqual(status_resp.json(), {"connected": False})


if __name__ == "__main__":
    unittest.main()
