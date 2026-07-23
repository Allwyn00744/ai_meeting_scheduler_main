"""
Unit and route tests for WhatsApp Notifications V1 settings: the
WhatsAppSettingsRepository, WhatsAppNotificationService.get_status/
update_settings, and the GET /whatsapp/status + PUT /whatsapp/settings
routes. Automatic notification hooks and the manual send/test
endpoints are covered separately in test_whatsapp_notifications.py.

Run with: python -m unittest tests.test_whatsapp_settings -v
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
from app.repositories.whatsapp_settings_repository import (  # noqa: E402
    WhatsAppSettingsRepository,
)
from app.schemas.whatsapp import WhatsAppSettingsUpdate  # noqa: E402
from app.services.whatsapp_notification_service import (  # noqa: E402
    WhatsAppNotificationService,
)


class WhatsAppSettingsTestCase(unittest.TestCase):

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

    def test_repository_get_by_user_id_returns_none_when_absent(self):
        db = self.SessionLocal()
        try:
            self.assertIsNone(
                WhatsAppSettingsRepository.get_by_user_id(db, self.owner_id)
            )
        finally:
            db.close()

    def test_repository_create_and_get_by_user_id(self):
        from app.models.whatsapp_settings import WhatsAppSettings

        db = self.SessionLocal()
        try:
            created = WhatsAppSettingsRepository.create(
                db,
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number="+15551234567",
                    is_enabled=True,
                ),
            )
            self.assertIsNotNone(created.id)

            fetched = WhatsAppSettingsRepository.get_by_user_id(
                db, self.owner_id,
            )
            self.assertEqual(fetched.phone_number, "+15551234567")
            self.assertTrue(fetched.is_enabled)
        finally:
            db.close()

    def test_repository_update_persists_changes(self):
        from app.models.whatsapp_settings import WhatsAppSettings

        db = self.SessionLocal()
        try:
            row = WhatsAppSettingsRepository.create(
                db,
                WhatsAppSettings(
                    user_id=self.owner_id,
                    phone_number="+15551234567",
                    is_enabled=False,
                ),
            )
            row.is_enabled = True
            WhatsAppSettingsRepository.update(db, row)

            fetched = WhatsAppSettingsRepository.get_by_user_id(
                db, self.owner_id,
            )
            self.assertTrue(fetched.is_enabled)
        finally:
            db.close()

    # ---- service ----

    def test_service_get_status_defaults_when_no_row(self):
        db = self.SessionLocal()
        try:
            result = WhatsAppNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                result, {"enabled": False, "phone_number": None},
            )
        finally:
            db.close()

    def test_service_update_settings_creates_row_on_first_use(self):
        db = self.SessionLocal()
        try:
            WhatsAppNotificationService.update_settings(
                db,
                self.owner_id,
                WhatsAppSettingsUpdate(
                    phone_number="+15559998888", is_enabled=True,
                ),
            )

            status_after = WhatsAppNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                status_after,
                {"enabled": True, "phone_number": "+15559998888"},
            )
        finally:
            db.close()

    def test_service_update_settings_patches_existing_row(self):
        db = self.SessionLocal()
        try:
            WhatsAppNotificationService.update_settings(
                db,
                self.owner_id,
                WhatsAppSettingsUpdate(
                    phone_number="+15559998888", is_enabled=True,
                ),
            )

            # Partial update: only toggling is_enabled off, phone
            # number must be left untouched.
            WhatsAppNotificationService.update_settings(
                db,
                self.owner_id,
                WhatsAppSettingsUpdate(is_enabled=False),
            )

            status_after = WhatsAppNotificationService.get_status(
                db, self.owner_id,
            )
            self.assertEqual(
                status_after,
                {"enabled": False, "phone_number": "+15559998888"},
            )
        finally:
            db.close()

    # ---- routes ----

    def test_get_status_route_defaults_when_unconfigured(self):
        response = self.client.get(
            "/whatsapp/status", headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"enabled": False, "phone_number": None},
        )

    def test_get_status_route_requires_auth(self):
        response = self.client.get("/whatsapp/status")
        self.assertEqual(response.status_code, 401)

    def test_put_settings_route_updates_phone_and_enabled(self):
        response = self.client.put(
            "/whatsapp/settings",
            json={"phone_number": "+15551112222", "is_enabled": True},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"enabled": True, "phone_number": "+15551112222"},
        )

        follow_up = self.client.get(
            "/whatsapp/status", headers=self.auth_headers,
        )
        self.assertEqual(
            follow_up.json(),
            {"enabled": True, "phone_number": "+15551112222"},
        )

    def test_put_settings_route_partial_update(self):
        self.client.put(
            "/whatsapp/settings",
            json={"phone_number": "+15551112222", "is_enabled": True},
            headers=self.auth_headers,
        )

        response = self.client.put(
            "/whatsapp/settings",
            json={"is_enabled": False},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"enabled": False, "phone_number": "+15551112222"},
        )

    def test_put_settings_route_requires_auth(self):
        response = self.client.put(
            "/whatsapp/settings",
            json={"phone_number": "+15551112222", "is_enabled": True},
        )
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
