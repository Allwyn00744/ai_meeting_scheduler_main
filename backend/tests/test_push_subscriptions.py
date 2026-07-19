"""
Unit and route tests for Push Notifications V1 subscriptions: the
PushSubscriptionRepository, PushNotificationService.get_status/
subscribe/unsubscribe, and the GET /push/status + POST /push/subscribe
+ DELETE /push/unsubscribe routes. Automatic notification hooks and the
manual test endpoint are covered separately in
test_push_notifications.py.

Run with: python -m unittest tests.test_push_subscriptions -v
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
from app.repositories.push_subscription_repository import (  # noqa: E402
    PushSubscriptionRepository,
)
from app.schemas.push import (  # noqa: E402
    PushSubscribeRequest,
    PushSubscriptionKeys,
)
from app.services.push_notification_service import (  # noqa: E402
    PushNotificationService,
)

FAKE_ENDPOINT_A = "https://fcm.googleapis.com/fcm/send/aaa"
FAKE_ENDPOINT_B = "https://fcm.googleapis.com/fcm/send/bbb"


class PushSubscriptionsTestCase(unittest.TestCase):

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

    # ---- repository ----

    def test_repository_get_by_user_id_returns_empty_when_absent(self):
        db = self.SessionLocal()
        try:
            self.assertEqual(
                PushSubscriptionRepository.get_by_user_id(db, self.owner_id),
                [],
            )
        finally:
            db.close()

    def test_repository_create_and_get_by_user_id(self):
        from app.models.push_subscription import PushSubscription

        db = self.SessionLocal()
        try:
            created = PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_A,
                    p256dh_key="p256dh-a",
                    auth_key="auth-a",
                ),
            )
            self.assertIsNotNone(created.id)

            fetched = PushSubscriptionRepository.get_by_user_id(
                db, self.owner_id,
            )
            self.assertEqual(len(fetched), 1)
            self.assertEqual(fetched[0].endpoint, FAKE_ENDPOINT_A)
            self.assertTrue(fetched[0].is_enabled)
        finally:
            db.close()

    def test_repository_supports_multiple_subscriptions_per_user(self):
        from app.models.push_subscription import PushSubscription

        db = self.SessionLocal()
        try:
            PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_A,
                    p256dh_key="p256dh-a",
                    auth_key="auth-a",
                ),
            )
            PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_B,
                    p256dh_key="p256dh-b",
                    auth_key="auth-b",
                ),
            )

            fetched = PushSubscriptionRepository.get_by_user_id(
                db, self.owner_id,
            )
            self.assertEqual(len(fetched), 2)
        finally:
            db.close()

    def test_repository_get_enabled_by_user_id_excludes_disabled(self):
        from app.models.push_subscription import PushSubscription

        db = self.SessionLocal()
        try:
            PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_A,
                    p256dh_key="p256dh-a",
                    auth_key="auth-a",
                    is_enabled=True,
                ),
            )
            PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_B,
                    p256dh_key="p256dh-b",
                    auth_key="auth-b",
                    is_enabled=False,
                ),
            )

            enabled = PushSubscriptionRepository.get_enabled_by_user_id(
                db, self.owner_id,
            )
            self.assertEqual(len(enabled), 1)
            self.assertEqual(enabled[0].endpoint, FAKE_ENDPOINT_A)
        finally:
            db.close()

    def test_repository_update_persists_changes(self):
        from app.models.push_subscription import PushSubscription

        db = self.SessionLocal()
        try:
            row = PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_A,
                    p256dh_key="p256dh-a",
                    auth_key="auth-a",
                    is_enabled=True,
                ),
            )
            row.is_enabled = False
            PushSubscriptionRepository.update(db, row)

            fetched = PushSubscriptionRepository.get_by_endpoint(
                db, self.owner_id, FAKE_ENDPOINT_A,
            )
            self.assertFalse(fetched.is_enabled)
        finally:
            db.close()

    def test_repository_delete_removes_row(self):
        from app.models.push_subscription import PushSubscription

        db = self.SessionLocal()
        try:
            row = PushSubscriptionRepository.create(
                db,
                PushSubscription(
                    user_id=self.owner_id,
                    endpoint=FAKE_ENDPOINT_A,
                    p256dh_key="p256dh-a",
                    auth_key="auth-a",
                ),
            )
            PushSubscriptionRepository.delete(db, row)

            self.assertIsNone(
                PushSubscriptionRepository.get_by_endpoint(
                    db, self.owner_id, FAKE_ENDPOINT_A,
                )
            )
        finally:
            db.close()

    # ---- service ----

    def test_service_get_status_defaults_when_no_rows(self):
        db = self.SessionLocal()
        try:
            result = PushNotificationService.get_status(db, self.owner_id)
            self.assertEqual(
                result, {"enabled": False, "subscription_count": 0},
            )
        finally:
            db.close()

    def test_service_subscribe_creates_row_on_first_use(self):
        db = self.SessionLocal()
        try:
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="p256dh-a", auth="auth-a"),
                ),
            )

            status_after = PushNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                status_after,
                {"enabled": True, "subscription_count": 1},
            )
        finally:
            db.close()

    def test_service_subscribe_upserts_existing_endpoint(self):
        db = self.SessionLocal()
        try:
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="old", auth="old"),
                ),
            )
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="new", auth="new"),
                ),
            )

            rows = PushSubscriptionRepository.get_by_user_id(
                db, self.owner_id,
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].p256dh_key, "new")
        finally:
            db.close()

    def test_service_subscribe_is_enabled_patches_existing_row(self):
        db = self.SessionLocal()
        try:
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="p256dh-a", auth="auth-a"),
                ),
            )
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="p256dh-a", auth="auth-a"),
                    is_enabled=False,
                ),
            )

            status_after = PushNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                status_after,
                {"enabled": False, "subscription_count": 1},
            )
        finally:
            db.close()

    def test_service_unsubscribe_removes_row(self):
        db = self.SessionLocal()
        try:
            PushNotificationService.subscribe(
                db,
                self.owner_id,
                PushSubscribeRequest(
                    endpoint=FAKE_ENDPOINT_A,
                    keys=PushSubscriptionKeys(p256dh="p256dh-a", auth="auth-a"),
                ),
            )
            result = PushNotificationService.unsubscribe(
                db, self.owner_id, FAKE_ENDPOINT_A,
            )
            self.assertTrue(result)

            status_after = PushNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                status_after,
                {"enabled": False, "subscription_count": 0},
            )
        finally:
            db.close()

    def test_service_unsubscribe_missing_endpoint_returns_false(self):
        db = self.SessionLocal()
        try:
            result = PushNotificationService.unsubscribe(
                db, self.owner_id, FAKE_ENDPOINT_A,
            )
            self.assertFalse(result)
        finally:
            db.close()

    # ---- routes ----

    def test_get_status_route_defaults_when_unconfigured(self):
        response = self.client.get(
            "/push/status", headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"enabled": False, "subscription_count": 0},
        )

    def test_get_status_route_requires_auth(self):
        response = self.client.get("/push/status")
        self.assertEqual(response.status_code, 401)

    def test_subscribe_route_creates_subscription(self):
        response = self.client.post(
            "/push/subscribe",
            json={
                "endpoint": FAKE_ENDPOINT_A,
                "keys": {"p256dh": "p256dh-a", "auth": "auth-a"},
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"enabled": True, "subscription_count": 1},
        )

    def test_subscribe_route_requires_auth(self):
        response = self.client.post(
            "/push/subscribe",
            json={
                "endpoint": FAKE_ENDPOINT_A,
                "keys": {"p256dh": "p256dh-a", "auth": "auth-a"},
            },
        )
        self.assertEqual(response.status_code, 401)

    def test_subscribe_route_is_idempotent_for_same_endpoint(self):
        for _ in range(2):
            response = self.client.post(
                "/push/subscribe",
                json={
                    "endpoint": FAKE_ENDPOINT_A,
                    "keys": {"p256dh": "p256dh-a", "auth": "auth-a"},
                },
                headers=self.auth_headers,
            )
        self.assertEqual(response.json()["subscription_count"], 1)

    def test_unsubscribe_route_removes_subscription(self):
        self.client.post(
            "/push/subscribe",
            json={
                "endpoint": FAKE_ENDPOINT_A,
                "keys": {"p256dh": "p256dh-a", "auth": "auth-a"},
            },
            headers=self.auth_headers,
        )

        response = self.client.request(
            "DELETE",
            "/push/unsubscribe",
            json={"endpoint": FAKE_ENDPOINT_A},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"enabled": False, "subscription_count": 0},
        )

    def test_unsubscribe_route_requires_auth(self):
        response = self.client.request(
            "DELETE",
            "/push/unsubscribe",
            json={"endpoint": FAKE_ENDPOINT_A},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
