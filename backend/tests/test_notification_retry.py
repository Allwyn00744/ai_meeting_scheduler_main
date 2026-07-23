"""
Unit tests for the retry behavior added to the notification integration
clients (SlackAPI.post_message, WhatsAppClient.send_text_message,
PushClient.send_notification, EmailService.send_email - see
test_email_notifications.py for the email-specific cases).

Each client now retries up to 3 attempts (tenacity, exponential
backoff) on a transport-level failure only (connection refused/reset,
timed out, or - for push - a 5xx from the push service) and never on a
failure that reached the remote service and was rejected for a reason
retrying can't fix (bad credentials, invalid recipient, expired
subscription). This exercises both branches directly against each
client, with `requests`/`webpush` mocked at the boundary so no network
call is made.

Run with: python -m unittest tests.test_notification_retry -v
(from the backend/ directory)
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402
from pywebpush import WebPushException  # noqa: E402

# Importing app.main (as every other test file in this suite does)
# registers every SQLAlchemy model on the shared declarative registry
# before any model is instantiated below - without it, instantiating
# SlackCredential in a fresh process fails to configure the User
# mapper's relationship to GoogleCredential (a string reference that
# is only resolvable once that module has been imported too).
from app.main import app  # noqa: E402,F401
from app.integrations.slack_client import SlackAPI, SlackAPIError  # noqa: E402
from app.integrations.whatsapp_client import WhatsAppClient  # noqa: E402
from app.integrations.push_client import PushClient  # noqa: E402
from app.models.slack_credential import SlackCredential  # noqa: E402


def _fake_response(status_code=200, json_body=None):
    response = MagicMock(spec=requests.Response)
    response.status_code = status_code
    response.json.return_value = json_body or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(response=response)
    else:
        response.raise_for_status.return_value = None
    return response


class SlackRetryTestCase(unittest.TestCase):

    def setUp(self):
        self.credential = SlackCredential(
            user_id=1,
            access_token="xoxb-fake",
            team_id="T1",
            team_name="Team",
            slack_user_id="U1",
            scopes="chat:write",
        )

    def test_connection_error_is_retried_then_succeeds(self):
        ok_response = _fake_response(200, {"ok": True})
        call_count = {"n": 0}

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise requests.exceptions.ConnectionError("refused")
            return ok_response

        with patch(
            "app.integrations.slack_client.requests.post",
            side_effect=_side_effect,
        ):
            result = SlackAPI.post_message(self.credential, "hello")

        self.assertEqual(call_count["n"], 3)
        self.assertTrue(result["ok"])

    def test_invalid_auth_is_not_retried(self):
        bad_response = _fake_response(200, {"ok": False, "error": "invalid_auth"})
        call_count = {"n": 0}

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            return bad_response

        with patch(
            "app.integrations.slack_client.requests.post",
            side_effect=_side_effect,
        ):
            with self.assertRaises(SlackAPIError):
                SlackAPI.post_message(self.credential, "hello")

        self.assertEqual(call_count["n"], 1)


class WhatsAppRetryTestCase(unittest.TestCase):

    def setUp(self):
        # whatsapp_configured is a computed @property (True only when
        # both fields below are non-blank) - patch the underlying
        # fields, not the property itself, which pydantic won't allow
        # setattr/delattr on.
        settings_patcher = patch.multiple(
            "app.integrations.whatsapp_client.settings",
            WHATSAPP_ACCESS_TOKEN="fake-token",
            WHATSAPP_PHONE_NUMBER_ID="123456",
            WHATSAPP_API_VERSION="v23.0",
        )
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

    def test_timeout_is_retried_then_succeeds(self):
        ok_response = _fake_response(200, {})
        call_count = {"n": 0}

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise requests.exceptions.Timeout("timed out")
            return ok_response

        with patch(
            "app.integrations.whatsapp_client.requests.post",
            side_effect=_side_effect,
        ):
            sent, detail = WhatsAppClient.send_text_message("+1555", "hi")

        self.assertEqual(call_count["n"], 2)
        self.assertTrue(sent)
        self.assertIsNone(detail)

    def test_meta_error_body_is_not_retried(self):
        error_response = _fake_response(
            200,
            {"error": {"message": "Recipient not in allowed list", "code": 131030}},
        )
        call_count = {"n": 0}

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            return error_response

        with patch(
            "app.integrations.whatsapp_client.requests.post",
            side_effect=_side_effect,
        ):
            sent, detail = WhatsAppClient.send_text_message("+1555", "hi")

        self.assertEqual(call_count["n"], 1)
        self.assertFalse(sent)
        self.assertIn("131030", detail)


class PushRetryTestCase(unittest.TestCase):

    def setUp(self):
        # push_configured is a computed @property (True only when both
        # VAPID keys are non-blank) - patch the underlying fields, not
        # the property itself, which pydantic won't allow setattr/
        # delattr on.
        settings_patcher = patch.multiple(
            "app.integrations.push_client.settings",
            VAPID_PRIVATE_KEY="fake-private-key",
            VAPID_PUBLIC_KEY="fake-public-key",
            VAPID_CLAIM_EMAIL="admin@example.com",
        )
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

    def test_connection_error_is_retried_then_succeeds(self):
        call_count = {"n": 0}

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise requests.exceptions.ConnectionError("refused")
            return None

        with patch(
            "app.integrations.push_client.webpush",
            side_effect=_side_effect,
        ):
            sent, detail = PushClient.send_notification(
                endpoint="https://fcm.example/aaa",
                p256dh_key="p256dh",
                auth_key="auth",
                title="Title",
                body="Body",
            )

        self.assertEqual(call_count["n"], 3)
        self.assertTrue(sent)
        self.assertIsNone(detail)

    def test_expired_subscription_is_not_retried(self):
        call_count = {"n": 0}
        expired_response = _fake_response(410)

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            raise WebPushException("Gone", response=expired_response)

        with patch(
            "app.integrations.push_client.webpush",
            side_effect=_side_effect,
        ):
            sent, detail = PushClient.send_notification(
                endpoint="https://fcm.example/aaa",
                p256dh_key="p256dh",
                auth_key="auth",
                title="Title",
                body="Body",
            )

        self.assertEqual(call_count["n"], 1)
        self.assertFalse(sent)
        self.assertIn("subscription expired", detail)

    def test_5xx_from_push_service_is_retried_then_succeeds(self):
        call_count = {"n": 0}
        server_error_response = _fake_response(503)

        def _side_effect(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise WebPushException("Unavailable", response=server_error_response)
            return None

        with patch(
            "app.integrations.push_client.webpush",
            side_effect=_side_effect,
        ):
            sent, detail = PushClient.send_notification(
                endpoint="https://fcm.example/aaa",
                p256dh_key="p256dh",
                auth_key="auth",
                title="Title",
                body="Body",
            )

        self.assertEqual(call_count["n"], 2)
        self.assertTrue(sent)


if __name__ == "__main__":
    unittest.main()
