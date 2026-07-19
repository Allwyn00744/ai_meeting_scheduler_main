from datetime import timezone

import requests

from app.models.zoom_credential import ZoomCredential

ZOOM_API_BASE_URL = "https://api.zoom.us/v2"

# Bounded so an unreachable/slow Zoom API can never stall a request
# indefinitely - requests has no default timeout of its own.
ZOOM_TIMEOUT_SECONDS = 10

# Per Zoom's Create Meeting API, "type": 2 is a scheduled meeting (as
# opposed to 1 = instant, 3 = recurring with no fixed time, 8 =
# recurring with a fixed time). This app never creates a native Zoom
# recurring series - SchedulerService already expands a "recurring"
# meeting request into N independent Meeting rows, so each occurrence
# gets its own type=2 scheduled Zoom meeting, mirroring how it already
# gets its own independent Google/Outlook calendar event.
ZOOM_MEETING_TYPE_SCHEDULED = 2


class ZoomAPI:

    @staticmethod
    def _headers(credential: ZoomCredential) -> dict:
        return {
            "Authorization": f"Bearer {credential.access_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _to_zoom_datetime(dt) -> str:
        # Zoom's Create/Update Meeting API wants start_time as a UTC
        # ISO 8601 string with a "Z" suffix, plus a separate `timezone`
        # field - normalize to UTC and strip tzinfo before formatting
        # so the two can't disagree, matching the approach already
        # used by OutlookCalendarAPI._to_graph_datetime.
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.isoformat() + "Z"

    @staticmethod
    def _duration_minutes(start_time, end_time) -> int:
        return max(1, round((end_time - start_time).total_seconds() / 60))

    @staticmethod
    def create_meeting(
        credential: ZoomCredential,
        title: str,
        description: str,
        start_time,
        end_time,
    ):
        # Zoom's Meetings API has no "location" or "attendees" field on
        # scheduled meetings (attendee invites require the separate,
        # approval-gated Registrants API) - a Zoom meeting is a video
        # room, not a calendar event, so only topic/agenda/timing are
        # sent here.
        payload = {
            "topic": title,
            "type": ZOOM_MEETING_TYPE_SCHEDULED,
            "start_time": ZoomAPI._to_zoom_datetime(start_time),
            "duration": ZoomAPI._duration_minutes(start_time, end_time),
            "timezone": "UTC",
            "agenda": description,
        }

        response = requests.post(
            f"{ZOOM_API_BASE_URL}/users/me/meetings",
            headers=ZoomAPI._headers(credential),
            json=payload,
            timeout=ZOOM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return response.json()

    @staticmethod
    def update_meeting(
        credential: ZoomCredential,
        meeting_id: str,
        title: str,
        description: str,
        start_time,
        end_time,
    ):
        payload = {
            "topic": title,
            "type": ZOOM_MEETING_TYPE_SCHEDULED,
            "start_time": ZoomAPI._to_zoom_datetime(start_time),
            "duration": ZoomAPI._duration_minutes(start_time, end_time),
            "timezone": "UTC",
            "agenda": description,
        }

        response = requests.patch(
            f"{ZOOM_API_BASE_URL}/meetings/{meeting_id}",
            headers=ZoomAPI._headers(credential),
            json=payload,
            timeout=ZOOM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        # Zoom's PATCH /meetings/{id} returns 204 No Content on success
        # (no updated resource body), unlike Google/Outlook's update
        # calls, which return the updated event. join_url/start_url are
        # stable for the lifetime of a meeting and never change on
        # update, so there is nothing to re-read from the response.
        return True

    @staticmethod
    def delete_meeting(
        credential: ZoomCredential,
        meeting_id: str,
    ):
        response = requests.delete(
            f"{ZOOM_API_BASE_URL}/meetings/{meeting_id}",
            headers=ZoomAPI._headers(credential),
            timeout=ZOOM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return True
