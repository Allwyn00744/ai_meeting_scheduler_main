"""
Integration tests for "Sign in with Google" (GET /auth/google/login,
GET /auth/google/callback) - distinct from the existing Google
*Calendar* connect flow under /google/* (app/api/google_routes.py),
which is untouched by this feature.

Mirrors the style of tests/test_slack_oauth.py: a real FastAPI app via
starlette's TestClient, backed by an in-memory SQLite DB. The Google
token exchange (flow.fetch_token) and id_token verification
(verify_oauth2_token) are mocked at the service boundary - state
generation/consumption, user find-or-create, and JWT issuance all run
for real.

Run with: python -m unittest tests.test_google_login_oauth -v
(from the backend/ directory)
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.core.rate_limit import limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


class GoogleLoginOAuthTestCase(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine,
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

        # Rate limiting is auto-disabled under `python -m unittest`
        # (see app/core/rate_limit.py) - explicitly confirm that stays
        # true here rather than assuming, since /auth/google/login and
        # /auth/google/callback are both decorated/adjacent to
        # @limiter.limit.
        self.assertFalse(limiter.enabled)

        self.client = TestClient(app, follow_redirects=False)

    def _start_login(self):
        resp = self.client.get("/auth/google/login")
        self.assertEqual(resp.status_code, 307)
        location = resp.headers["location"]
        state = location.split("state=")[1].split("&")[0]
        return state

    def test_login_redirects_to_google_with_state(self):
        resp = self.client.get("/auth/google/login")
        self.assertEqual(resp.status_code, 307)
        self.assertIn("accounts.google.com", resp.headers["location"])
        self.assertIn("state=", resp.headers["location"])

    def test_login_does_not_require_auth(self):
        # The whole point of this endpoint - a visitor with no
        # session at all must be able to reach it.
        resp = self.client.get("/auth/google/login")
        self.assertEqual(resp.status_code, 307)

    def test_callback_missing_state_redirects_to_error(self):
        resp = self.client.get("/auth/google/callback")
        self.assertEqual(resp.status_code, 307)
        self.assertIn("google=error", resp.headers["location"])

    def test_callback_invalid_state_redirects_to_error(self):
        resp = self.client.get(
            "/auth/google/callback",
            params={"state": "not-a-real-state", "code": "fake-code"},
        )
        self.assertEqual(resp.status_code, 307)
        self.assertIn("google=error", resp.headers["location"])

    def test_callback_creates_new_user_and_issues_token(self):
        state = self._start_login()

        fake_flow = MagicMock()
        fake_flow.fetch_token.return_value = None
        fake_flow.credentials.id_token = "fake-id-token"

        with patch(
            "app.api.auth_routes.GoogleLoginOAuthService.create_flow",
            return_value=fake_flow,
        ), patch(
            "app.api.auth_routes.verify_oauth2_token",
            return_value={
                "email": "newuser@example.com",
                "email_verified": True,
                "name": "New User",
            },
        ):
            callback_resp = self.client.get(
                "/auth/google/callback",
                params={"state": state, "code": "fake-code"},
            )

        self.assertEqual(callback_resp.status_code, 307)
        location = callback_resp.headers["location"]
        self.assertIn("/auth/google/callback#token=", location)

        token = location.split("#token=")[1]
        me_resp = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.json()["email"], "newuser@example.com")
        self.assertEqual(me_resp.json()["name"], "New User")

    def test_callback_logs_in_existing_user_by_email(self):
        register_resp = self.client.post(
            "/auth/register",
            json={
                "name": "Existing User",
                "email": "existing@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        existing_user_id = register_resp.json()["id"]

        state = self._start_login()

        fake_flow = MagicMock()
        fake_flow.fetch_token.return_value = None
        fake_flow.credentials.id_token = "fake-id-token"

        with patch(
            "app.api.auth_routes.GoogleLoginOAuthService.create_flow",
            return_value=fake_flow,
        ), patch(
            "app.api.auth_routes.verify_oauth2_token",
            return_value={
                "email": "existing@example.com",
                "email_verified": True,
                "name": "Existing User (Google)",
            },
        ):
            callback_resp = self.client.get(
                "/auth/google/callback",
                params={"state": state, "code": "fake-code"},
            )

        token = callback_resp.headers["location"].split("#token=")[1]
        me_resp = self.client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_resp.json()["id"], existing_user_id)
        # Signing in via Google must never rename an existing account.
        self.assertEqual(me_resp.json()["name"], "Existing User")

    def test_callback_rejects_unverified_email(self):
        state = self._start_login()

        fake_flow = MagicMock()
        fake_flow.fetch_token.return_value = None
        fake_flow.credentials.id_token = "fake-id-token"

        with patch(
            "app.api.auth_routes.GoogleLoginOAuthService.create_flow",
            return_value=fake_flow,
        ), patch(
            "app.api.auth_routes.verify_oauth2_token",
            return_value={
                "email": "unverified@example.com",
                "email_verified": False,
                "name": "Unverified",
            },
        ):
            callback_resp = self.client.get(
                "/auth/google/callback",
                params={"state": state, "code": "fake-code"},
            )

        self.assertIn("google=error", callback_resp.headers["location"])

    def test_state_is_single_use(self):
        state = self._start_login()

        fake_flow = MagicMock()
        fake_flow.fetch_token.return_value = None
        fake_flow.credentials.id_token = "fake-id-token"

        with patch(
            "app.api.auth_routes.GoogleLoginOAuthService.create_flow",
            return_value=fake_flow,
        ), patch(
            "app.api.auth_routes.verify_oauth2_token",
            return_value={
                "email": "reuse@example.com",
                "email_verified": True,
                "name": "Reuse",
            },
        ):
            first_resp = self.client.get(
                "/auth/google/callback",
                params={"state": state, "code": "fake-code"},
            )
            self.assertIn("#token=", first_resp.headers["location"])

            second_resp = self.client.get(
                "/auth/google/callback",
                params={"state": state, "code": "fake-code"},
            )

        self.assertIn("google=error", second_resp.headers["location"])


if __name__ == "__main__":
    unittest.main()
