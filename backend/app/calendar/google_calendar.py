import uuid
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.core.config import settings
from app.models.google_credential import GoogleCredential


class GoogleCalendarAPI:

    @staticmethod
    def get_calendar_service(
        credential: GoogleCredential,
    ):
        credentials = Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri=credential.token_uri,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=credential.scopes.split(","),
        )

        return build(
            "calendar",
            "v3",
            credentials=credentials,
        )

    @staticmethod
    def create_calendar_event(
        credential: GoogleCredential,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
        attendee_emails: list[str] | None = None,
    ):
        service = GoogleCalendarAPI.get_calendar_service(
            credential
        )

        event = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {
                "dateTime": start_time.isoformat(),
            },
            "end": {
                "dateTime": end_time.isoformat(),
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {
                        "type": "hangoutsMeet",
                    },
                }
            },
        }

        if attendee_emails:
            event["attendees"] = [
                {"email": email} for email in attendee_emails
            ]

        created_event = (
            service.events()
            .insert(
                calendarId="primary",
                body=event,
                conferenceDataVersion=1,
            )
            .execute()
        )

        return created_event
    @staticmethod
    def update_calendar_event(
        credential: GoogleCredential,
        event_id: str,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
    ):
        service = GoogleCalendarAPI.get_calendar_service(
            credential
        )

        event = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {
                "dateTime": start_time.isoformat(),
            },
            "end": {
                "dateTime": end_time.isoformat(),
            },
        }

        updated_event = (
            service.events()
            .update(
                calendarId="primary",
                eventId=event_id,
                body=event,
            )
            .execute()
        )

        return updated_event
    @staticmethod
    def delete_calendar_event(
        credential: GoogleCredential,
        event_id: str,
    ):
        service = GoogleCalendarAPI.get_calendar_service(
            credential
        )

        service.events().delete(
            calendarId="primary",
            eventId=event_id,
        ).execute()

        return True