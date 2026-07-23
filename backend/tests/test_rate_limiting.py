"""
Integration test for rate limiting (slowapi) on the auth endpoints -
see app/core/rate_limit.py and the @limiter.limit(...) decorators in
app/api/auth_routes.py.

Run with: python -m unittest tests.test_rate_limiting -v
(from the backend/ directory)
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402


class RateLimitingTestCase(unittest.TestCase):

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

        # Rate limiting is auto-disabled under `python -m unittest` (see
        # app/core/rate_limit.py) so the rest of the suite's setUp
        # calls (many register/login their own users) don't trip a
        # shared bucket - explicitly re-enable it here to actually
        # exercise the feature, and reset its counters so one test
        # method's exhausted limit doesn't bleed into the next.
        limiter.enabled = True
        limiter.reset()
        self.addCleanup(setattr, limiter, "enabled", False)

        self.client = TestClient(app)

    def test_login_is_rate_limited_after_five_attempts_per_minute(self):
        for _ in range(5):
            resp = self.client.post(
                "/auth/login",
                json={"email": "nobody@example.com", "password": "wrong"},
            )
            self.assertEqual(resp.status_code, 401)

        sixth_resp = self.client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
        )
        self.assertEqual(sixth_resp.status_code, 429)

    def test_register_is_rate_limited_after_five_attempts_per_minute(self):
        for i in range(5):
            resp = self.client.post(
                "/auth/register",
                json={
                    "name": f"User {i}",
                    "email": f"user{i}@example.com",
                    "password": "correct horse battery staple",
                    "timezone": "UTC",
                },
            )
            self.assertEqual(resp.status_code, 201)

        sixth_resp = self.client.post(
            "/auth/register",
            json={
                "name": "One Too Many",
                "email": "toomany@example.com",
                "password": "correct horse battery staple",
                "timezone": "UTC",
            },
        )
        self.assertEqual(sixth_resp.status_code, 429)

    def test_unrelated_routes_are_not_rate_limited(self):
        # /auth/me isn't decorated with @limiter.limit - hitting it
        # repeatedly must never 429, proving the limiter only applies
        # where explicitly opted in.
        for _ in range(10):
            resp = self.client.get("/auth/me")
            self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
