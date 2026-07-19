from sqlalchemy.orm import Session
from app.core.config import settings

from app.models.google_credential import GoogleCredential
from app.repositories.google_credential_repository import GoogleCredentialRepository
from fastapi import HTTPException, status

from app.calendar.google_calendar import GoogleCalendarAPI

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError, TransportError
from googleapiclient.errors import HttpError
from datetime import timezone

import logging

logger = logging.getLogger(__name__)


class GoogleCalendarService:

    @staticmethod
    def save_google_credentials(
        db: Session,
        user_id: int,
        credentials,
    ):
        existing = GoogleCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        if existing:
            existing.access_token = credentials.token
            existing.refresh_token = credentials.refresh_token
            existing.token_uri = credentials.token_uri
            existing.scopes = ",".join(credentials.scopes)
            existing.expiry = credentials.expiry

            return GoogleCredentialRepository.update(
                db,
                existing,
            )

        credential = GoogleCredential(
            user_id=user_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            scopes=",".join(credentials.scopes),
            expiry=credentials.expiry,
        )

        return GoogleCredentialRepository.create(
            db,
            credential,
        )

    @staticmethod
    def update_google_calendar_event(
        db: Session,
        meeting,
    ):
        credential = (
            GoogleCredentialRepository.get_by_user_id(
                db,
                meeting.owner_id,
            )
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        credential = GoogleCalendarService.refresh_google_token(
            db,
            credential,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        if not meeting.google_event_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google event not found.",
            )

        try:
            event = GoogleCalendarAPI.update_calendar_event(
                credential=credential,
                event_id=meeting.google_event_id,
                title=meeting.title,
                description=meeting.description or "",
                start_time=meeting.start_time,
                end_time=meeting.end_time,
                location=meeting.location,
            )
        except HttpError as exc:
            logger.warning(
                "Google Calendar update_calendar_event failed. "
                "meeting_id=%s status=%s",
                meeting.id,
                getattr(exc, "status_code", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to update the event on Google Calendar.",
            )

        logger.info(
            "Google Calendar event updated. meeting_id=%s event_id=%s",
            meeting.id,
            meeting.google_event_id,
        )
        return event

    @staticmethod
    def create_google_calendar_event(
        db: Session,
        user_id: int,
        title: str,
        description: str,
        start_time,
        end_time,
        location: str | None = None,
        attendee_emails: list[str] | None = None,
    ):
        credential = (
            GoogleCredentialRepository.get_by_user_id(
                db,
                user_id,
            )
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        credential = GoogleCalendarService.refresh_google_token(
            db,
            credential,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        try:
            event = GoogleCalendarAPI.create_calendar_event(
                credential=credential,
                title=title,
                description=description,
                start_time=start_time,
                end_time=end_time,
                location=location,
                attendee_emails=attendee_emails,
            )
        except HttpError as exc:
            logger.warning(
                "Google Calendar create_calendar_event failed. "
                "user_id=%s status=%s",
                user_id,
                getattr(exc, "status_code", "unknown"),
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to create the event on Google Calendar.",
            )

        logger.info(
            "Google Calendar event created. user_id=%s event_id=%s",
            user_id,
            event.get("id"),
        )

        return event

    @staticmethod
    def delete_google_calendar_event(
        db: Session,
        meeting,
    ):
        credential = (
            GoogleCredentialRepository.get_by_user_id(
                db,
                meeting.owner_id,
            )
        )
        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        credential = GoogleCalendarService.refresh_google_token(
            db,
            credential,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account not connected.",
            )

        if not meeting.google_event_id:
            return

        try:
            GoogleCalendarAPI.delete_calendar_event(
                credential=credential,
                event_id=meeting.google_event_id,
            )
        except HttpError as exc:
            status_code = getattr(exc, "status_code", None)

            # Already gone on Google's side (e.g. deleted manually by
            # the user in their calendar) - treat as success rather
            # than blocking our own deletion on a stale reference.
            if status_code == 410 or status_code == 404:
                logger.info(
                    "Google Calendar event already absent. "
                    "meeting_id=%s event_id=%s",
                    meeting.id,
                    meeting.google_event_id,
                )
                return

            logger.warning(
                "Google Calendar delete_calendar_event failed. "
                "meeting_id=%s status=%s",
                meeting.id,
                status_code,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to delete the event on Google Calendar.",
            )

        logger.info(
            "Google Calendar event deleted. meeting_id=%s event_id=%s",
            meeting.id,
            meeting.google_event_id,
        )

    @staticmethod
    def refresh_google_token(
        db: Session,
        credential: GoogleCredential,
    ):
        expiry = credential.expiry

        if expiry is not None and expiry.tzinfo is not None:
            expiry = (
                expiry
                .astimezone(timezone.utc)
                .replace(tzinfo=None)
            )

        credentials = Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri=credential.token_uri,
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            scopes=credential.scopes.split(","),
            expiry=expiry,
        )

        if credentials.expired and credentials.refresh_token:
            logger.info(
                "Refreshing expired Google OAuth token. user_id=%s",
                credential.user_id,
            )

            try:
                credentials.refresh(Request())
            except (RefreshError, TransportError):
                # Never log the exception object directly here - the
                # underlying library can include request/response
                # details in its message. A refresh failure almost
                # always means the user revoked access or the refresh
                # token is no longer valid, so surface a clean,
                # actionable error instead.
                logger.warning(
                    "Google OAuth token refresh failed. user_id=%s",
                    credential.user_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Google account access has expired or been "
                        "revoked. Please reconnect your Google "
                        "account."
                    ),
                )

            credential.access_token = credentials.token
            credential.expiry = credentials.expiry.replace(
                tzinfo=timezone.utc
            )

            credential = GoogleCredentialRepository.update(
                db,
                credential,
            )

            logger.info(
                "Google OAuth token refreshed successfully. user_id=%s",
                credential.user_id,
            )

        return credential

    @staticmethod
    def get_connection_status(db: Session, user_id: int) -> dict:
        """
        Used by GET /google/status. Returns whether this user has a
        stored Google credential, without attempting to refresh or
        validate the token (a cheap, read-only check for the Settings
        UI to render Connected/Not connected).
        """
        credential = GoogleCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        return {
            "connected": credential is not None,
        }

    @staticmethod
    def disconnect(db: Session, user_id: int) -> None:
        """
        Used by DELETE /google/disconnect. Removes the stored
        credential row. This does not revoke the token on Google's
        side (no token revocation call is made) - it only stops this
        app from using it, matching the "Disconnect" action shown in
        the Settings UI.
        """
        credential = GoogleCredentialRepository.get_by_user_id(
            db,
            user_id,
        )

        if credential is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Google account is not connected.",
            )

        GoogleCredentialRepository.delete(db, credential)
