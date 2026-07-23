import requests

from app.models.outlook_credential import OutlookCredential

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# Bounded so an unreachable/slow Graph API can never stall a request
# indefinitely - requests has no default timeout of its own.
GRAPH_TIMEOUT_SECONDS = 10

# Per Microsoft Graph's event resource, this is the value that turns a
# plain Outlook calendar event into a Teams meeting - there is no
# separate Teams meeting resource created here (deliberately not using
# the standalone /me/onlineMeetings API).
ONLINE_MEETING_PROVIDER_TEAMS = "teamsForBusiness"


class TeamsMeetingAPI:

    @staticmethod
    def _headers(credential: OutlookCredential) -> dict:
        return {
            "Authorization": f"Bearer {credential.access_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def enable_teams_meeting(
        credential: OutlookCredential,
        event_id: str,
    ) -> dict:
        """
        Turns an existing Outlook calendar event into a Teams meeting
        by setting isOnlineMeeting/onlineMeetingProvider on it. The
        response's onlineMeeting.joinUrl is the Teams join link -
        Graph populates it as part of this same PATCH, with no
        separate call needed.
        """
        payload = {
            "isOnlineMeeting": True,
            "onlineMeetingProvider": ONLINE_MEETING_PROVIDER_TEAMS,
        }

        response = requests.patch(
            f"{GRAPH_BASE_URL}/me/events/{event_id}",
            headers=TeamsMeetingAPI._headers(credential),
            json=payload,
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return response.json()

    @staticmethod
    def disable_teams_meeting(
        credential: OutlookCredential,
        event_id: str,
    ) -> dict:
        """
        Turns the Teams meeting off for an existing Outlook event
        without deleting the event itself - used to unlink Teams from
        a meeting (DELETE /teams/sync) while leaving the Outlook
        calendar entry in place.
        """
        payload = {
            "isOnlineMeeting": False,
        }

        response = requests.patch(
            f"{GRAPH_BASE_URL}/me/events/{event_id}",
            headers=TeamsMeetingAPI._headers(credential),
            json=payload,
            timeout=GRAPH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()

        return response.json()
