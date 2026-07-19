from datetime import timezone

import requests

from app.models.outlook_credential import OutlookCredential

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# Bounded so an unreachable/slow Graph API can never stall a request
# indefinitely - requests has no default timeout of its own.
GRAPH_TIMEOUT_SECONDS = 10


class OutlookCalendarAPI:

    @staticmethod
    def _headers(credential: OutlookCredential) -> dict:
        return {
            "Authorization": f"Bearer {credential.access_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _to_graph_datetime(dt) -> dict:
        # Graph wants a bare (no offset) dateTime string plus a
        # separate timeZone property, rather than an offset-suffixed
        # ISO 8601 string - normalize to UTC and strip tzinfo so the
        # two can't disagree.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return {"dateTime": dt.isoformat(), "timeZone": "UTC"}

    @staticmethod
    def create_calendar_event(
        credential: OutlookCredential,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
        attendee_emails: list[str] | None = None,
    ):
        event = {
            "subject": title,
            "body": {
                "contentType": "text",
                "content": description,
            },
            "start": OutlookCalendarAPI._to_graph_datetime(start_time),
            "end": OutlookCalendarAPI._to_graph_datetime(end_time),
        }

        if location:
            event["location"] = {"displayName": location}

        if attendee_emails:
            event["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in attendee_emails
            ]

        response = requests.post(
            f"{GRAPH_BASE_URL}/me/events",
            headers=OutlookCalendarAPI._headers(credential),
            json=event,
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return response.json()

    @staticmethod
    def update_calendar_event(
        credential: OutlookCredential,
        event_id: str,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
    ):
        event = {
            "subject": title,
            "body": {
                "contentType": "text",
                "content": description,
            },
            "start": OutlookCalendarAPI._to_graph_datetime(start_time),
            "end": OutlookCalendarAPI._to_graph_datetime(end_time),
        }

        if location:
            event["location"] = {"displayName": location}

        response = requests.patch(
            f"{GRAPH_BASE_URL}/me/events/{event_id}",
            headers=OutlookCalendarAPI._headers(credential),
            json=event,
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return response.json()

    @staticmethod
    def delete_calendar_event(
        credential: OutlookCredential,
        event_id: str,
    ):
        response = requests.delete(
            f"{GRAPH_BASE_URL}/me/events/{event_id}",
            headers=OutlookCalendarAPI._headers(credential),
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return True
